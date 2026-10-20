package runtime

import (
	"bufio"
	"crypto/rand"
	"io"
	"log"
	"os"
	"strings"
)

// Each engine process owns its console. Log events share the encoded RPC pipe.
type consoleCapture struct {
	input, output            *os.File
	previousOut, previousErr *os.File
	previousLogger           io.Writer
	marker                   string
	ack                      chan struct{}
	done                     chan struct{}
}

func captureConsole(emit func(string)) (*consoleCapture, error) {
	input, output, err := os.Pipe()
	if err != nil {
		return nil, err
	}
	c := &consoleCapture{input: input, output: output, previousOut: os.Stdout, previousErr: os.Stderr,
		previousLogger: log.Writer(), marker: "\x00" + rand.Text() + "\x00", ack: make(chan struct{}), done: make(chan struct{})}
	os.Stdout, os.Stderr = output, output
	log.SetOutput(output)
	go func() {
		defer close(c.done)
		reader := bufio.NewReader(input)
		for {
			line, readErr := reader.ReadString('\n')
			line = strings.TrimSuffix(line, "\n")
			barrier := strings.HasSuffix(line, c.marker)
			if barrier {
				line = strings.TrimSuffix(line, c.marker)
			}
			if line != "" {
				if len(line) > 65536 {
					line = line[:65536] + " [Yatori 日志超过 64 KiB，后续内容已截断]"
				}
				emit(strings.TrimSuffix(line, "\r"))
			}
			if barrier {
				c.ack <- struct{}{}
			}
			if readErr != nil {
				return
			}
		}
	}()
	return c, nil
}

// Drain console writes before the operation result so callers can close safely.
func (c *consoleCapture) flush() {
	if _, err := io.WriteString(c.output, c.marker+"\n"); err == nil {
		select {
		case <-c.ack:
		case <-c.done:
		}
	}
}

func (c *consoleCapture) close() {
	os.Stdout, os.Stderr = c.previousOut, c.previousErr
	log.SetOutput(c.previousLogger)
	c.output.Close()
	<-c.done
	c.input.Close()
}
