// SPDX-License-Identifier: MIT
// Copyright (c) 2023 ChangBaiQi
// Adapted from yatori-go-console logic/xuexitong/XueXiTongPart.go.
// Source commits and service adaptations are recorded in console-upstream.json.
package consolelogic

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"

	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/models/ctype"
	lg "github.com/yatori-dev/yatori-go-core/utils/log"
)

const Commit = "017711107803f5232fea59446a5b8c801d4ca8b2"

var ErrStructure = errors.New("console response structure changed")
var ErrRemote = errors.New("console operation was rejected")

// AssessmentReady follows writeCourseWorkAndExam and accepts existing API labels.
func AssessmentReady(kind, status string) bool {
	if status == "待做" || status == "未完成" || status == "未提交" || status == "待考试" || status == "进行中" {
		return true
	}
	return kind == "work" && (status == "未交" || status == "待重做") || kind == "exam" && status == "待重考"
}

type Runner struct {
	Cache        *yatori.XueXiTUserCache
	Context      context.Context
	Now          func() time.Time
	Wait         func(time.Duration) error
	Progress     func(float64)
	MediaClient  string
	AccountLabel string
	CourseTitle  string
	ChapterTitle string
}

func (r Runner) Log(title string, text ...interface{}) {
	account := r.AccountLabel
	if account == "" {
		account = r.Cache.Name
	}
	parts := []interface{}{"[学习通][", account, "] 【", r.CourseTitle, "】"}
	if r.ChapterTitle != "" {
		parts = append(parts, "【", r.ChapterTitle, "】")
	}
	if title != "" {
		parts = append(parts, "【", title, "】")
	}
	parts = append(parts, " ")
	lg.Print(lg.INFO, append(parts, text...)...)
}

// ChapterPage retains ParseWorkQuestionAction's specific alternate read path.
func (r Runner) ChapterPage(point *yatori.PointWorkDto) (string, error) {
	page, err := r.Cache.WorkFetchQuestion(point, 0, nil)
	if err != nil && strings.Contains(err.Error(), `<p class="blankTips">无效的权限,code=2</p>`) {
		r.Log("", "章节测验读取入口返回权限提示，尝试备用读取入口")
		return r.Cache.WorkFetch2Question(point, 0, nil)
	}
	return page, err
}

func response(raw string) (map[string]interface{}, error) {
	var data map[string]interface{}
	if json.Unmarshal([]byte(raw), &data) != nil || data == nil {
		return nil, ErrStructure
	}
	return data, nil
}

// ExecuteMedia follows ExecuteVideo / ExecuteAudio: resume, report, and wait
// for isPassed at the end, with a bounded final confirmation window.
func (r Runner) ExecuteMedia(p *yatori.PointVideoDto, audio bool) error {
	raw, err := r.Cache.VideoDtoFetch(p, 0, nil)
	if err != nil {
		return err
	}
	data, err := response(raw)
	if err != nil {
		return err
	}
	if data["status"] != "success" {
		return ErrRemote
	}
	p.DToken, _ = data["dtoken"].(string)
	duration, ok := data["duration"].(float64)
	if !ok || duration <= 0 || duration != math.Trunc(duration) || duration > 86400 || p.DToken == "" || p.PlayTime < 0 || p.PlayTime > int(duration) {
		return ErrStructure
	}
	p.Duration = int(duration)
	started, origin := r.Now(), p.PlayTime
	nextReport := origin
	var endedAt time.Time
	limit := max(500, p.Duration/2)
	for {
		if err := r.Context.Err(); err != nil {
			return err
		}
		position := min(p.Duration, origin+max(0, int(r.Now().Sub(started).Seconds())))
		if position >= nextReport {
			if audio {
				raw, err = r.Cache.AudioPhoneSubmitTimeApi(p, position, 0, 0, nil)
			} else if r.MediaClient == "mobile" {
				raw, err = r.Cache.VideoSubmitStudyTimePEApi(p, position, 0, 0, nil)
			} else {
				raw, err = r.Cache.VideoSubmitStudyTimeApi(p, position, 0, 0, nil)
			}
			if err != nil {
				return err
			}
			data, err = response(raw)
			if err != nil {
				return err
			}
			passed, known := data["isPassed"].(bool)
			if !known {
				return ErrStructure
			}
			if data["status"] == false {
				return ErrRemote
			}
			r.Log(p.Title, "提交状态：", strconv.FormatBool(passed), " 观看时间：", fmt.Sprintf("%d/%d", position, p.Duration), " 观看进度：", fmt.Sprintf("%.2f%%", float64(position)/float64(p.Duration)*100))
			if passed && position >= p.Duration {
				return nil
			}
			nextReport = position + 58
			if position == p.Duration {
				if endedAt.IsZero() {
					endedAt = r.Now()
				}
				overtime := int(r.Now().Sub(endedAt).Seconds())
				r.Log(p.Title, "过超时间：", fmt.Sprintf("%d/%d", overtime, limit), " 等待服务端完成确认")
				if overtime >= limit {
					r.Log(p.Title, "过超提交失败，自动进行下一任务...")
					return nil
				}
				nextReport = position
				if err := r.Wait(5 * time.Second); err != nil {
					return err
				}
				continue
			}
			nextReport = min(nextReport, p.Duration)
		}
		r.Progress(math.Min(1, float64(position)/float64(p.Duration)))
		if err := r.Wait(time.Second); err != nil {
			return err
		}
	}
}

func (r Runner) ExecuteDocument(p *yatori.PointDocumentDto) error {
	var raw string
	var err error
	switch p.Type {
	case ctype.InsertBook:
		raw, err = r.Cache.DocumentDtoReadingBookReport(p, 0, nil)
	case ctype.InsertReadV2:
		raw, err = r.Cache.ReadV2PointPeReport(p, 0, nil)
	default:
		raw, err = r.Cache.DocumentDtoReadingReport(p, 0, nil)
	}
	return r.resourceResult(p.Title, "文档阅览状态：", raw, err)
}

func (r Runner) ExecuteHyperlink(p *yatori.PointHyperlinkDto) error {
	raw, err := r.Cache.HyperlinkDtoCompleteReport(p, 0, nil)
	return r.resourceResult(p.Title, "外链任务点状态：", raw, err)
}

func (r Runner) resourceResult(title, label, raw string, err error) error {
	if err != nil {
		return err
	}
	data, err := response(raw)
	if err != nil {
		return err
	}
	passed, known := data["status"].(bool)
	if !known {
		return ErrStructure
	}
	r.Log(title, label, strconv.FormatBool(passed))
	if !passed {
		return ErrRemote
	}
	return nil
}
