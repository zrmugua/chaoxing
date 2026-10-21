package runtime

import (
	"net/url"
	"strings"

	"chaoxing-console/engine/consolelogic"
	"github.com/PuerkitoBio/goquery"
)

type Assessment struct {
	ID        string `json:"id"`
	Kind      string `json:"kind"`
	Title     string `json:"title"`
	Status    string `json:"status"`
	Remaining string `json:"remaining"`
	Ready     bool   `json:"ready"`
}
type assessmentTarget struct {
	course Course
	params url.Values
	status string
}

func (r *Runtime) assessments(course Course, work, exam bool) ([]Assessment, error) {
	result := []Assessment{}
	for _, kind := range []string{"work", "exam"} {
		if kind == "work" && !work || kind == "exam" && !exam {
			continue
		}
		var page string
		var err error
		if kind == "work" {
			page, err = r.cache.PullWorkListHtmlApi(field(course, "courseId"), field(course, "clazzId"), field(course, "cpi"), 0, nil)
		} else {
			page, err = r.cache.PullExamListHtmlApi(field(course, "courseId"), field(course, "clazzId"), field(course, "cpi"), 0, nil)
		}
		if err != nil {
			return nil, r.coreError(err)
		}
		items, err := assessmentList(page, kind)
		if err != nil {
			return nil, err
		}
		doc, _ := goquery.NewDocumentFromReader(strings.NewReader(page))
		doc.Find("ul.nav li[data]").Each(func(_ int, row *goquery.Selection) {
			raw, _ := row.Attr("data")
			parsed, e := url.Parse(raw)
			if e != nil {
				return
			}
			params := parsed.Query()
			id := params.Get("taskrefId")
			if id == "" {
				return
			}
			r.assessmentsByID[kind+":"+id] = assessmentTarget{course: course, params: params, status: strings.TrimSpace(row.Find("div span").First().Text())}
		})
		result = append(result, items...)
	}
	return result, nil
}

func assessmentList(page, kind string) ([]Assessment, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(page))
	if err != nil {
		return nil, failure("parser_changed")
	}
	result := []Assessment{}
	list := doc.Find("ul.nav")
	if list.Length() == 0 || list.Find("li").Length() == 0 {
		// Only an explicit empty-list marker establishes an empty result.
		label := "作业"
		if kind == "exam" {
			label = "考试"
		}
		if strings.Contains(page, "暂无"+label) || strings.Contains(page, "没有相关"+label) {
			return result, nil
		}
		return nil, failure("parser_changed")
	}
	valid := true
	list.Find("li").Each(func(_ int, row *goquery.Selection) {
		raw, _ := row.Attr("data")
		parsed, parseErr := url.Parse(raw)
		title := strings.TrimSpace(row.Find("div p").First().Text())
		if parseErr != nil || title == "" {
			valid = false
			return
		}
		params := parsed.Query()
		id := params.Get("taskrefId")
		if id == "" {
			id = params.Get("workId")
		}
		if id == "" {
			id = params.Get("examId")
		}
		if id == "" {
			valid = false
			return
		}
		spans := row.Find("div span")
		status := strings.TrimSpace(spans.Eq(0).Text())
		result = append(result, Assessment{ID: id, Kind: kind, Title: title, Status: status, Remaining: strings.TrimSpace(spans.Eq(1).Text()), Ready: consolelogic.AssessmentReady(kind, status)})
	})
	if !valid {
		return nil, failure("parser_changed")
	}
	return result, nil
}
