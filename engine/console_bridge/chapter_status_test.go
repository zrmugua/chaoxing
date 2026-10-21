//go:build consolebridge

package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

func TestChapterMetadataAndCounts(t *testing.T) {
	for _, raw := range []string{
		`{"101":{"totalcount":2,"finishcount":2,"unfinishcount":0}}`,
		`{"msg":"成功","status":true,"101":{"totalcount":2,"finishcount":2,"unfinishcount":0},"requestId":"fixture"}`,
		`{"msg":"成功","data":{"101":{"totalcount":"2","finishcount":"2","unfinishcount":"0"}}}`,
	} {
		points, err := decodeChapterPoints(raw, []int{101})
		if err != nil || points[101].Total != 2 || !points[101].completed() {
			t.Fatalf("valid chapter response: points=%v err=%v", points, err)
		}
	}
}

func TestChapterErrorMessagesRemainAvailable(t *testing.T) {
	for _, raw := range []string{
		`{"msg":"登录状态已失效"}`,
		`{"status":false,"msg":"登录状态已失效","101":{"totalcount":1,"finishcount":1,"unfinishcount":0}}`,
		`{"success":"false","message":"登录状态已失效"}`,
		`{"result":0,"errorMsg":"登录状态已失效"}`,
		`{"data":{"msg":"登录状态已失效"}}`,
	} {
		points, err := decodeChapterPoints(raw, []int{101})
		if points != nil || err == nil || !strings.Contains(err.Error(), "登录状态已失效") {
			t.Fatalf("expected platform rejection with reason: points=%v err=%v", points, err)
		}
	}
}

func TestIncompleteAndMalformedChapterResponses(t *testing.T) {
	for _, test := range []struct{ name, raw string }{
		{"empty", `{}`},
		{"null", `null`},
		{"array", `[]`},
		{"html", `<html>private-server-content</html>`},
		{"wrong-chapter", `{"102":{"totalcount":1,"finishcount":1,"unfinishcount":0}}`},
		{"string-chapter", `{"101":"unavailable"}`},
		{"null-chapter", `{"101":null}`},
		{"missing-count", `{"101":{"finishcount":1,"unfinishcount":0}}`},
		{"null-count", `{"101":{"totalcount":null,"finishcount":1,"unfinishcount":0}}`},
		{"decimal-count", `{"101":{"totalcount":1.5,"finishcount":1,"unfinishcount":0}}`},
		{"negative-count", `{"101":{"totalcount":1,"finishcount":-1,"unfinishcount":0}}`},
		{"invalid-count", `{"101":{"totalcount":1,"finishcount":1,"unfinishcount":"unknown"}}`},
		{"overflow-count", `{"101":{"totalcount":999999999999999999999999,"finishcount":1,"unfinishcount":0}}`},
		{"inconsistent-count", `{"101":{"totalcount":1,"finishcount":2,"unfinishcount":0}}`},
		{"trailing-json", `{"101":{"totalcount":1,"finishcount":1,"unfinishcount":0}}{}`},
	} {
		t.Run(test.name, func(t *testing.T) {
			points, err := decodeChapterPoints(test.raw, []int{101})
			if err == nil || points != nil || strings.Contains(err.Error(), "private-server-content") {
				t.Fatalf("invalid response produced a snapshot or raw response: points=%v err=%v", points, err)
			}
		})
	}
	points, err := decodeChapterPoints(`{"101":{"totalcount":1,"finishcount":1,"unfinishcount":0}}`, []int{101, 102})
	if err == nil || points != nil {
		t.Fatal("a partial course must not replace the previous progress snapshot")
	}
}

func TestChapterCompletionRequiresConfirmedCounts(t *testing.T) {
	for _, test := range []struct {
		total, finished, unfinished int
		completed                   bool
	}{
		{2, 2, 0, true}, {2, 1, 1, false}, {0, 0, 0, false}, {0, 0, 1, false}, {1, 1, 1, false},
	} {
		raw := fmt.Sprintf(`{"101":{"totalcount":%d,"finishcount":%d,"unfinishcount":%d}}`, test.total, test.finished, test.unfinished)
		points, err := decodeChapterPoints(raw, []int{101})
		if err != nil || points[101].completed() != test.completed {
			t.Fatalf("completion mismatch: points=%v err=%v", points, err)
		}
	}
}

func TestChapterQueriesUseBoundedBatches(t *testing.T) {
	nodes := make([]int, 205)
	for i := range nodes {
		nodes[i] = i + 1
	}
	var sizes []int
	points, err := queryChapterPoints(nodes, func(batch []int) (string, error) {
		sizes = append(sizes, len(batch))
		response := map[string]any{"msg": "成功"}
		for _, id := range batch {
			response[fmt.Sprint(id)] = map[string]int{"totalcount": 1, "finishcount": 1, "unfinishcount": 0}
		}
		encoded, _ := json.Marshal(response)
		return string(encoded), nil
	})
	if err != nil || len(points) != 205 || !reflect.DeepEqual(sizes, []int{100, 100, 5}) {
		t.Fatalf("unexpected batches: sizes=%v count=%d err=%v", sizes, len(points), err)
	}
	for _, id := range nodes {
		if !points[id].completed() {
			t.Fatalf("chapter %d missing", id)
		}
	}
}

func TestChapterBatchFailureIsAtomic(t *testing.T) {
	nodes := make([]int, 201)
	for i := range nodes {
		nodes[i] = i + 1
	}
	for _, failure := range []string{"platform", "network"} {
		calls := 0
		points, err := queryChapterPoints(nodes, func(batch []int) (string, error) {
			calls++
			if calls == 2 {
				if failure == "network" {
					return "", errors.New("network fixture failure")
				}
				return `{"msg":"访问频繁，请稍后重试"}`, nil
			}
			response := map[string]any{}
			for _, id := range batch {
				response[fmt.Sprint(id)] = map[string]int{"totalcount": 1, "finishcount": 1, "unfinishcount": 0}
			}
			encoded, _ := json.Marshal(response)
			return string(encoded), nil
		})
		if err == nil || points != nil || calls != 2 {
			t.Fatalf("partial result after %s failure: %v %v calls=%d", failure, points, err, calls)
		}
	}
}
