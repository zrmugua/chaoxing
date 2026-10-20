package runtime

import (
	"encoding/json"
	"math"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/models/ctype"
	"github.com/yatori-dev/yatori-go-core/utils"
)

func decodeDTO(value any, target any) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return failure("parser_changed")
	}
	if json.Unmarshal(raw, target) != nil {
		return failure("parser_changed")
	}
	return nil
}
func (r *Runtime) canonical(job Job) (Job, error) {
	known, ok := r.jobs[job.ChapterID+":"+job.ID]
	if !ok {
		return Job{}, failure("parser_changed")
	}
	r.currentCard = &known.Card
	return known, nil
}
func (r *Runtime) execute(course Course, supplied Job) error {
	job, err := r.canonical(supplied)
	if err != nil {
		return err
	}
	if job.Passed {
		return nil
	}
	if job.Metadata["completion_unknown"] == true {
		return failure("job_state_unknown")
	}
	switch job.Kind {
	case "video", "audio":
		return r.video(job)
	case "hyperlink":
		var p yatori.PointHyperlinkDto
		if err := decodeDTO(job.Metadata["hyperlink"], &p); err != nil {
			return err
		}
		raw, err := r.cache.HyperlinkDtoCompleteReport(&p, 0, nil)
		if err != nil {
			return r.coreError(err)
		}
		data, err := parseObject(raw)
		if err != nil {
			return err
		}
		if data["status"] != true {
			return failure("remote_error")
		}
		return nil
	case "document", "read":
		var p yatori.PointDocumentDto
		if err := decodeDTO(job.Metadata["document"], &p); err != nil {
			return err
		}
		var raw string
		if p.Type == ctype.InsertBook {
			raw, err = r.cache.DocumentDtoReadingBookReport(&p, 0, nil)
		} else if p.Type == ctype.InsertReadV2 {
			raw, err = r.cache.ReadV2PointPeReport(&p, 0, nil)
		} else {
			raw, err = r.cache.DocumentDtoReadingReport(&p, 0, nil)
		}
		if err != nil {
			return r.coreError(err)
		}
		data, err := parseObject(raw)
		if err != nil {
			return err
		}
		if data["status"] != true {
			return failure("remote_error")
		}
		return nil
	default:
		return failure("manual_required")
	}
}

func (r *Runtime) video(job Job) error {
	var p yatori.PointVideoDto
	if err := decodeDTO(job.Metadata["video"], &p); err != nil {
		return err
	}
	raw, err := r.cache.VideoDtoFetch(&p, 0, nil)
	if err != nil {
		return r.coreError(err)
	}
	data, err := parseObject(raw)
	if err != nil {
		return err
	}
	if data["status"] != "success" {
		return failure("remote_error")
	}
	p.DToken = field(data, "dtoken")
	p.Duration = number(data["duration"])
	if p.DToken == "" || p.Duration <= 0 || p.PlayTime < 0 || p.PlayTime > p.Duration {
		return failure("parser_changed")
	}
	interval := number(job.Defaults["reportTimeInterval"])
	if interval < 5 {
		interval = 60
	}
	if interval > 120 {
		interval = 120
	}
	started := r.now()
	origin := p.PlayTime
	nextReport, finalReports := origin, 0
	for {
		if err := r.ctx.Err(); err != nil {
			return err
		}
		elapsed := int(r.now().Sub(started).Seconds())
		position := origin + elapsed
		if position > p.Duration {
			position = p.Duration
		}
		if position >= nextReport || position == p.Duration {
			var report string
			var err error
			if job.Kind == "audio" {
				report, err = r.cache.AudioPhoneSubmitTimeApi(&p, position, 0, 0, nil)
			} else if r.mediaClient == "mobile" {
				report, err = r.cache.VideoSubmitStudyTimePEApi(&p, position, 0, 0, nil)
			} else {
				report, err = r.cache.VideoSubmitStudyTimeApi(&p, position, 0, 0, nil)
			}
			if err != nil {
				return r.coreError(err)
			}
			result, err := parseObject(report)
			if err != nil {
				return err
			}
			if result["isPassed"] == true {
				return nil
			}
			if result["status"] == false {
				return failure("remote_error")
			}
			nextReport = position + interval
			if position == p.Duration {
				finalReports++
				if finalReports >= 2 {
					return nil
				}
				nextReport = position
			}
		}
		r.progress(math.Min(1, float64(position)/float64(p.Duration)))
		if err := r.wait(time.Second); err != nil {
			return err
		}
	}
}

func (r *Runtime) questions(course Course, supplied Job) ([]map[string]any, error) {
	job, err := r.canonical(supplied)
	if err != nil {
		return nil, err
	}
	if job.Kind != "workid" {
		return nil, failure("unsupported_job")
	}
	var p yatori.PointWorkDto
	if err := decodeDTO(job.Metadata["work"], &p); err != nil {
		return nil, err
	}
	page, err := r.cache.WorkFetchQuestion(&p, 0, nil)
	if err != nil {
		return nil, r.coreError(err)
	}
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(page))
	if err != nil {
		return nil, failure("parser_changed")
	}
	result := []map[string]any{}
	for _, question := range utils.ParseQuestionSets(doc) {
		qdoc, parseErr := goquery.NewDocumentFromReader(strings.NewReader(question.HTML))
		if parseErr != nil {
			continue
		}
		item := qdoc.Selection
		title := strings.TrimSpace(item.Find(".Py-m1-title .workTextWrap").Text())
		id := question.ID
		if title == "" || id == "" {
			continue
		}
		options := []string{}
		item.Find(".answerList li").Each(func(_ int, option *goquery.Selection) {
			if value := strings.TrimSpace(option.Text()); value != "" {
				options = append(options, value)
			}
		})
		kind := strings.Trim(strings.TrimSpace(item.Find(".quesType").First().Text()), "[]【】")
		if kind == "" {
			kind = "unknown"
		}
		result = append(result, map[string]any{"id": id, "title": title, "type": kind, "options": options})
	}
	if len(result) == 0 {
		return nil, failure("manual_required")
	}
	return result, nil
}
