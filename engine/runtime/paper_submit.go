package runtime

import (
	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/que-core/qentity"
	"strconv"
	"strings"
)

func (r *Runtime) saveAnswers(id string, answers map[string][]string, submit, requireComplete bool) (map[string]any, error) {
	p := r.papers[id]
	if p == nil {
		return nil, failure("parser_changed")
	}
	complete := true
	answered := 0
	for _, q := range p.Questions {
		a := answers[q.ID]
		valid := q.Supported && len(a) > 0
		for _, s := range a {
			if strings.TrimSpace(s) == "" {
				valid = false
			}
		}
		if q.Code == "2" && (q.Blanks == 0 || len(a) != q.Blanks) {
			valid = false
		}
		if q.Code == "0" && len(a) != 1 {
			valid = false
		}
		if q.Code == "0" || q.Code == "1" {
			for _, s := range a {
				found := false
				for _, opt := range q.Options {
					if s == opt {
						found = true
					}
				}
				if !found {
					valid = false
				}
			}
		}
		if q.Code == "3" && (len(a) != 1 || (a[0] != "正确" && a[0] != "错误")) {
			valid = false
		}
		if !valid {
			complete = false
			delete(answers, q.ID)
		} else {
			answered++
		}
	}
	if answered == 0 {
		return map[string]any{"saved": false, "submitted": false, "complete": false}, nil
	}
	doSubmit := submit && (!requireComplete || complete)
	if p.Kind == "chapter" {
		if err := r.submitChapter(p, answers, doSubmit); err != nil {
			return nil, err
		}
	} else {
		last := -1
		for i, q := range p.Questions {
			if len(answers[q.ID]) > 0 {
				last = i
			}
		}
		for i, q := range p.Questions {
			a := answers[q.ID]
			if len(a) == 0 {
				continue
			}
			f := p.fields[i]
			var raw string
			var err error
			if p.Kind == "work" {
				entity := yatori.XXTWorkQuestionSubmitEntity{}
				reflectFields(&entity, f)
				entity.WordId = f["workid"]
				entity.AnswerId = f["workanswerid"]
				entity.Question = qentity.Question{Type: q.Type, Content: q.Title, Options: q.Options, Answers: a}
				if entity.WordId == "" || entity.AnswerId == "" || entity.Enc == "" || entity.EncWork == "" {
					return nil, failure("parser_changed")
				}
				raw, err = r.cache.SubmitWorkAnswerApi(&entity, !(doSubmit && i == last), 0, nil)
			} else {
				entity := yatori.XXTExamQuestionSubmitEntity{}
				reflectFields(&entity, f)
				entity.Question = qentity.Question{Type: q.Type, Content: q.Title, Options: q.Options, Answers: a}
				if entity.TestPaperId == "" || entity.TestUserRelationId == "" || entity.Enc == "" || entity.EncRemainTime == "" {
					return nil, failure("parser_changed")
				}
				raw, err = r.cache.SubmitExamAnswerApi(&entity, !(doSubmit && i == last))
			}
			if err != nil {
				return nil, r.coreError(err)
			}
			if !acknowledged(raw) {
				return nil, failure("remote_error")
			}
		}
	}
	delete(r.papers, id)
	r.consoleRunner(p.course, p.job.ChapterID).Log("", "试卷答案处理完毕 保存状态：true 交卷状态：", strconv.FormatBool(doSubmit))
	return map[string]any{"saved": true, "submitted": doSubmit, "complete": complete}, nil
}
