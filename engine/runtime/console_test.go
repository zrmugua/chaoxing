package runtime

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"strings"
	"testing"

	yatorilog "github.com/yatori-dev/yatori-go-core/utils/log"
)

func TestServeKeepsConsoleEventsSeparateFromRPCResults(t *testing.T) {
	requests, send := io.Pipe()
	receive, results := io.Pipe()
	done := make(chan struct{})
	go func() {
		defer close(done)
		defer results.Close()
		Serve(requests, results)
	}()
	defer func() { send.Close(); receive.Close(); <-done }()
	decoder := json.NewDecoder(receive)
	fmt.Fprintln(send, `{"id":1,"op":"initialize","args":{"credentials":{},"cookies":[]}}`)
	var initialized Response
	if err := decoder.Decode(&initialized); err != nil || !initialized.OK {
		t.Fatal("initialize response unavailable")
	}
	fmt.Fprintln(os.Stdout, "Yatori console fixture")
	fmt.Fprintln(send, `{"id":2,"op":"export_cookies"}`)
	var event, result Response
	if err := decoder.Decode(&event); err != nil || event.Event != "log" || event.Message != "Yatori console fixture" {
		t.Fatal("console output was not encoded as a log event")
	}
	if err := decoder.Decode(&result); err != nil || !result.OK || result.ID != 2 {
		t.Fatal("console output affected the RPC response")
	}
	fmt.Fprintln(send, `{"id":3,"op":"list_jobs","args":{"chapter":{"need_unlock":true}}}`)
	var restricted Response
	if err := decoder.Decode(&restricted); err != nil || restricted.Code != "manual_required" || restricted.Reason != "chapter_locked" {
		t.Fatal("manual verification reason did not reach the RPC caller")
	}
}

func TestConsoleCaptureFlushesOriginalOutput(t *testing.T) {
	previousOut, previousErr, previousLogger := os.Stdout, os.Stderr, log.Writer()
	var lines []string
	capture, err := captureConsole(func(line string) { lines = append(lines, line) })
	if err != nil {
		t.Fatal(err)
	}
	fmt.Fprintln(os.Stdout, "原始控制台输出")
	fmt.Fprintln(os.Stderr, "原始错误输出")
	log.Print("standard logger output")
	yatorilog.Print(yatorilog.INFO, "Yatori logger output")
	fmt.Fprint(os.Stdout, "partial line")
	capture.flush()
	capture.close()
	if os.Stdout != previousOut || os.Stderr != previousErr || log.Writer() != previousLogger {
		t.Fatal("console writers were not restored")
	}
	if len(lines) != 5 || lines[0] != "原始控制台输出" || lines[1] != "原始错误输出" || !strings.Contains(lines[2], "standard logger output") || !strings.Contains(lines[3], "Yatori logger output") || lines[4] != "partial line" {
		t.Fatalf("unexpected console lines: %q", lines)
	}
}

func TestConsoleCaptureContinuesAfterLargeLine(t *testing.T) {
	var lines []string
	capture, err := captureConsole(func(line string) { lines = append(lines, line) })
	if err != nil {
		t.Fatal(err)
	}
	fmt.Fprintln(os.Stdout, strings.Repeat("x", 100000))
	fmt.Fprintln(os.Stdout, "next line")
	capture.flush()
	capture.close()
	if len(lines) != 2 || len(lines[0]) > 66000 || !strings.Contains(lines[0], "64 KiB") || lines[1] != "next line" {
		t.Fatal("large console output affected subsequent records")
	}
}
