package runtime

import (
	"encoding/json"

	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
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
	if job.Metadata["completion_unknown"] == true {
		return failure("job_state_unknown")
	}
	job, err = r.refreshJob(course, job)
	if err != nil {
		return err
	}
	if job.Passed {
		return nil
	}
	if job.Metadata["completion_unknown"] == true {
		return failure("job_state_unknown")
	}
	runner := r.consoleRunner(course, job.ChapterID)
	switch job.Kind {
	case "video", "audio":
		var p yatori.PointVideoDto
		if err := decodeDTO(job.Metadata["video"], &p); err != nil {
			return err
		}
		return r.coreResult(runner.ExecuteMedia(&p, job.Kind == "audio"))
	case "document", "read":
		var p yatori.PointDocumentDto
		if err := decodeDTO(job.Metadata["document"], &p); err != nil {
			return err
		}
		return r.coreResult(runner.ExecuteDocument(&p))
	case "hyperlink":
		var p yatori.PointHyperlinkDto
		if err := decodeDTO(job.Metadata["hyperlink"], &p); err != nil {
			return err
		}
		return r.coreResult(runner.ExecuteHyperlink(&p))
	default:
		return failure("unsupported_job")
	}
}

func (r *Runtime) coreResult(err error) error {
	if err == nil && r.lastFailure == nil {
		return nil
	}
	return r.coreError(err)
}

func (r *Runtime) questions(course Course, supplied Job) ([]map[string]any, error) {
	paper, err := r.chapterPaper(course, supplied)
	if err != nil {
		return nil, err
	}
	result := []map[string]any{}
	for _, q := range paper.Questions {
		result = append(result, map[string]any{"id": q.ID, "title": q.Title, "type": q.Type, "code": q.Code, "options": q.Options, "blanks": q.Blanks, "supported": q.Supported})
	}
	return result, nil
}
