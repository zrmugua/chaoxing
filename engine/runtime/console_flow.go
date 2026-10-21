package runtime

import (
	"strconv"
	"strings"

	"chaoxing-console/engine/consolelogic"
	"github.com/PuerkitoBio/goquery"
	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/que-core/qtype"
	"github.com/yatori-dev/yatori-go-core/utils"
)

func (r *Runtime) consoleRunner(course Course, chapterID string) consolelogic.Runner {
	return consolelogic.Runner{Cache: r.cache, Context: r.ctx, Now: r.now, Wait: r.wait, Progress: r.progress,
		MediaClient: r.mediaClient, AccountLabel: r.logLabel, CourseTitle: field(course, "title"), ChapterTitle: r.chapterTitles[chapterID]}
}

// Console nodeRun refreshes a task's own card immediately before executing it.
func (r *Runtime) refreshJob(course Course, previous Job) (Job, error) {
	classID, err := courseInt(course, "clazzId")
	if err != nil {
		return Job{}, err
	}
	courseID, err := courseInt(course, "courseId")
	if err != nil {
		return Job{}, err
	}
	cpi, err := courseInt(course, "cpi")
	if err != nil {
		return Job{}, err
	}
	page, err := r.cache.PageMobileChapterCard(classID, courseID, number(previous.ChapterID), previous.Card, cpi, 0, nil)
	if err != nil {
		return Job{}, r.coreError(err)
	}
	payload, err := taskData(page)
	if err != nil {
		return Job{}, err
	}
	for _, entry := range array(payload["attachments"]) {
		job, keep, err := r.decodeJob(course, Chapter{ID: previous.ChapterID}, previous.Card, object(entry), object(payload["defaults"]))
		if err != nil {
			return Job{}, err
		}
		if keep && job.ID == previous.ID {
			if job.Kind != previous.Kind {
				return Job{}, failure("parser_changed")
			}
			r.jobs[job.ChapterID+":"+job.ID] = job
			return job, nil
		}
	}
	return Job{}, failure("jobs_missing")
}

func consoleChapterQuestions(doc *goquery.Document, parsed yatori.Question) ([]PaperQuestion, error) {
	byID := map[string]PaperQuestion{}
	add := func(id, text, code string, options []string, blanks int) {
		byID[id] = PaperQuestion{ID: id, Title: strings.TrimSpace(text), Code: code, Type: questionTypes[code], Options: options, Blanks: blanks, Supported: true}
	}
	for _, q := range parsed.Choice {
		code := "0"
		if q.Type == qtype.MultipleChoice {
			code = "1"
		}
		options := []string{}
		for ch := 'A'; ch <= 'N'; ch++ {
			if value := q.Options[string(ch)]; value != "" {
				options = append(options, value)
			} else {
				break
			}
		}
		add(q.Qid, q.Text, code, options, 0)
	}
	for _, q := range parsed.Judge {
		add(q.Qid, q.Text, "3", []string{}, 0)
	}
	for _, q := range parsed.Fill {
		add(q.Qid, q.Text, "2", []string{}, len(q.OpFromAnswer))
	}
	for _, q := range parsed.Short {
		add(q.Qid, q.Text, "4", []string{}, 0)
	}
	for _, q := range parsed.TermExplanation {
		add(q.Qid, q.Text, "5", []string{}, 0)
	}
	for _, q := range parsed.Essay {
		add(q.Qid, q.Text, "6", []string{}, 0)
	}
	result := []PaperQuestion{}
	seen := map[string]bool{}
	for _, part := range utils.ParseQuestionSets(doc) {
		if !safeID.MatchString(part.ID) || seen[part.ID] {
			return nil, failure("parser_changed")
		}
		seen[part.ID] = true
		qdoc, err := goquery.NewDocumentFromReader(strings.NewReader(part.HTML))
		if err != nil {
			return nil, failure("parser_changed")
		}
		q, known := byID[part.ID]
		if !known {
			q = PaperQuestion{ID: part.ID, Title: strings.TrimSpace(qdoc.Find(".workTextWrap").Text()), Type: "待确认题型", Options: []string{}}
		}
		fields := hiddenFields(qdoc)
		label := qdoc.Find(".quesType").First().Text()
		if !strings.Contains(label, q.Type) && !(q.Code == "0" && strings.Contains(label, "投票题")) && !(q.Code == "3" && strings.Contains(label, "辨析题")) && !(q.Code == "2" && strings.Contains(label, "分录题")) {
			q.Supported = false
		}
		if code := fields["answertype"+part.ID]; code != "" && code != q.Code {
			q.Supported = false
		}
		if q.Code == "2" && q.Blanks == 0 {
			q.Blanks = qdoc.Find(".blankItemName, .fillInBlank").Length()
			if q.Blanks == 0 {
				q.Blanks, _ = strconv.Atoi(fields["tiankongsize"+q.ID])
			}
		}
		if (q.Code == "0" || q.Code == "1") && (len(q.Options) < 2 || qdoc.Find(".answerList li").Length() != len(q.Options)) || q.Code == "2" && q.Blanks < 1 {
			q.Supported = false
		}
		if q.Title == "" {
			return nil, failure("parser_changed")
		}
		result = append(result, q)
	}
	return result, nil
}
