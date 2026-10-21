//go:build consolebridge

package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

type chapterPointStatus struct {
	Total      int
	Finished   int
	Unfinished int
}

func (point chapterPointStatus) completed() bool {
	return point.Total > 0 && point.Total == point.Finished && point.Unfinished == 0
}

func chapterResponseMessage(payload map[string]json.RawMessage) string {
	for _, key := range []string{"msg", "message", "errorMsg", "error"} {
		var message string
		if json.Unmarshal(payload[key], &message) == nil && strings.TrimSpace(message) != "" {
			return strings.Join(strings.Fields(message), " ")
		}
	}
	return ""
}

func chapterResponseRejected(payload map[string]json.RawMessage) bool {
	for _, key := range []string{"status", "success", "result"} {
		raw := strings.TrimSpace(string(payload[key]))
		if raw == "false" || raw == "0" || strings.EqualFold(raw, `"false"`) || raw == `"0"` {
			return true
		}
	}
	return false
}

func chapterResponseError(reason string, payload map[string]json.RawMessage) error {
	if message := chapterResponseMessage(payload); message != "" {
		return fmt.Errorf("%s；平台提示：%s", reason, message)
	}
	return fmt.Errorf("%s", reason)
}

func chapterCount(payload map[string]json.RawMessage, key string) (int, error) {
	raw := strings.TrimSpace(string(payload[key]))
	if strings.HasPrefix(raw, `"`) {
		var value string
		if err := json.Unmarshal(payload[key], &value); err != nil {
			return 0, fmt.Errorf("章节进度字段 %s 格式无效", key)
		}
		raw = strings.TrimSpace(value)
	}
	// Counts are non-negative decimal integers, whether encoded as numbers or strings.
	if raw == "" || strings.IndexFunc(raw, func(r rune) bool { return r < '0' || r > '9' }) >= 0 {
		return 0, fmt.Errorf("章节进度字段 %s 缺失或格式无效", key)
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("章节进度字段 %s 超出有效范围", key)
	}
	return value, nil
}

// decodeChapterPoints separates response metadata from requested chapter IDs.
// A failed or partial response produces no progress snapshot.
func decodeChapterPoints(raw string, nodes []int) (map[int]chapterPointStatus, error) {
	var payload map[string]json.RawMessage
	if json.Unmarshal([]byte(raw), &payload) != nil || payload == nil {
		return nil, fmt.Errorf("章节进度接口返回了无法识别的数据，请稍后重试")
	}
	if chapterResponseRejected(payload) {
		return nil, chapterResponseError("平台未返回章节进度", payload)
	}
	var nested map[string]json.RawMessage
	if data, exists := payload["data"]; exists && string(data) != "null" {
		if err := json.Unmarshal(data, &nested); err != nil {
			return nil, chapterResponseError("章节进度数据格式无法识别", payload)
		}
		if chapterResponseRejected(nested) {
			return nil, chapterResponseError("平台未返回章节进度", nested)
		}
	}
	points := make(map[int]chapterPointStatus, len(nodes))
	errorPayload := payload
	if chapterResponseMessage(payload) == "" && chapterResponseMessage(nested) != "" {
		errorPayload = nested
	}
	for _, id := range nodes {
		if id <= 0 {
			return nil, fmt.Errorf("章节编号无效，请重新同步课程列表")
		}
		key := strconv.Itoa(id)
		entry, exists := payload[key]
		if !exists {
			entry, exists = nested[key]
		}
		if !exists {
			return nil, chapterResponseError("平台返回的章节进度不完整，请稍后重试", errorPayload)
		}
		var values map[string]json.RawMessage
		if json.Unmarshal(entry, &values) != nil || values == nil {
			return nil, chapterResponseError("章节进度数据格式无法识别", payload)
		}
		total, err := chapterCount(values, "totalcount")
		if err != nil {
			return nil, err
		}
		finished, err := chapterCount(values, "finishcount")
		if err != nil {
			return nil, err
		}
		unfinished, err := chapterCount(values, "unfinishcount")
		if err != nil {
			return nil, err
		}
		if total == 0 && unfinished > 0 {
			// This is the upstream endpoint's zero-total unfinished-node form.
			total = unfinished
		}
		if finished > total {
			return nil, fmt.Errorf("平台返回的章节完成数与总数不一致，请稍后重试")
		}
		points[id] = chapterPointStatus{Total: total, Finished: finished, Unfinished: unfinished}
	}
	return points, nil
}

// Fetch bounded batches and return only after every requested chapter was decoded.
func queryChapterPoints(nodes []int, fetch func([]int) (string, error)) (map[int]chapterPointStatus, error) {
	points := make(map[int]chapterPointStatus, len(nodes))
	for start := 0; start < len(nodes); start += 100 {
		end := start + 100
		if end > len(nodes) {
			end = len(nodes)
		}
		batch := nodes[start:end]
		raw, err := fetch(batch)
		if err != nil {
			return nil, err
		}
		decoded, err := decodeChapterPoints(raw, batch)
		if err != nil {
			return nil, err
		}
		for id, point := range decoded {
			points[id] = point
		}
	}
	return points, nil
}
