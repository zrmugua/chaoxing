package runtime

import (
	"bufio"
	metadata "chaoxing-console/engine"
	"context"
	"encoding/json"
	"io"
	"log"
	"os"
	"sync"
	"time"
)

var UpstreamCommit = metadata.PinnedCommit()

type Request struct {
	ID   int64           `json:"id"`
	Op   string          `json:"op"`
	Args json.RawMessage `json:"args"`
}
type Response struct {
	ID        int64   `json:"id"`
	OK        bool    `json:"ok"`
	Data      any     `json:"data,omitempty"`
	Code      string  `json:"code,omitempty"`
	Event     string  `json:"event,omitempty"`
	Value     float64 `json:"value,omitempty"`
	CardIndex *int    `json:"card_index,omitempty"`
}

func ServeStdio() { Serve(os.Stdin, os.Stdout) }

// Serve owns one account for the lifetime of an isolated engine process.
func Serve(input io.Reader, output io.Writer) {
	log.SetOutput(io.Discard)
	previousOut, previousErr := os.Stdout, os.Stderr
	defer func() { os.Stdout, os.Stderr = previousOut, previousErr }()
	if sink, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0); err == nil {
		os.Stdout, os.Stderr = sink, sink
		defer sink.Close()
	}
	encoder := json.NewEncoder(output)
	var mutex sync.Mutex
	emit := func(r Response) { mutex.Lock(); defer mutex.Unlock(); _ = encoder.Encode(r) }
	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 4096), 2_000_000)
	var state *Runtime
	for scanner.Scan() {
		var request Request
		if json.Unmarshal(scanner.Bytes(), &request) != nil {
			emit(Response{Code: "adapter_error"})
			continue
		}
		result := Response{ID: request.ID}
		if request.Op == "initialize" {
			if state != nil {
				result.Code = "adapter_error"
			} else {
				var err error
				state, err = New(request.Args)
				if err != nil {
					result.Code = errorCode(err)
				} else {
					result.OK = true
					result.Data = map[string]string{"engine": "yatori", "upstream": UpstreamCommit}
				}
			}
		} else if state == nil {
			result.Code = "adapter_error"
		} else {
			duration := 170 * time.Second
			if request.Op == "execute" {
				duration = state.executionTimeout
			}
			state.ctx, state.cancel = context.WithTimeout(context.Background(), duration)
			state.progress = func(value float64) { emit(Response{ID: request.ID, Event: "progress", Value: value}) }
			data, err := state.Dispatch(request.Op, request.Args)
			state.cancel()
			if err != nil {
				result.Code = errorCode(err)
				if state.currentCard != nil && *state.currentCard >= 0 && *state.currentCard <= 10000 {
					result.CardIndex = state.currentCard
				}
			} else {
				result.OK = true
				result.Data = data
			}
		}
		emit(result)
	}
}
