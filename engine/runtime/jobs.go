package runtime

import (
	"encoding/json"
	"regexp"
	"strconv"
	"strings"

	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/models/ctype"
)

var assignment = regexp.MustCompile(`(?:window\.AttachmentSetting|\bmArg)\s*=\s*(\{)`)

func taskData(page string) (map[string]any, error) {
	if strings.Contains(page, "章节未开放") {
		return nil, requireManual("chapter_locked")
	}
	var selected map[string]any
	offset := 0
	for offset < len(page) {
		match := assignment.FindStringSubmatchIndex(page[offset:])
		if match == nil {
			break
		}
		start := offset + match[2]
		decoder := json.NewDecoder(strings.NewReader(page[start:]))
		var data map[string]any
		if decoder.Decode(&data) != nil {
			return nil, failure("parser_changed")
		}
		offset = start + int(decoder.InputOffset())
		if len(data) == 0 {
			continue
		}
		if selected != nil {
			previous, _ := json.Marshal(selected)
			current, _ := json.Marshal(data)
			if string(previous) != string(current) {
				return nil, failure("parser_changed")
			}
		}
		selected = data
	}
	if selected == nil {
		return nil, failure("parser_changed")
	}
	if _, ok := selected["attachments"].([]any); !ok {
		return nil, failure("parser_changed")
	}
	if _, ok := selected["defaults"].(map[string]any); !ok {
		return nil, failure("parser_changed")
	}
	return selected, nil
}

func (r *Runtime) listJobs(course Course, chapter Chapter) ([]Job, error) {
	if chapter.Locked {
		return nil, requireManual("chapter_locked")
	}
	courseID, err := courseInt(course, "courseId")
	if err != nil {
		return nil, err
	}
	classID, err := courseInt(course, "clazzId")
	if err != nil {
		return nil, err
	}
	cpi, err := courseInt(course, "cpi")
	if err != nil {
		return nil, err
	}
	chapterID, err := strconv.Atoi(chapter.ID)
	if err != nil || chapterID <= 0 {
		return nil, failure("parser_changed")
	}
	raw, err := r.cache.FetchChapterCords([]int{chapterID}, 0, courseID, 0, nil)
	if err != nil {
		return nil, r.coreError(err)
	}
	if r.lastFailure != nil {
		return nil, r.lastFailure
	}
	listing, err := parseObject(raw)
	if err != nil {
		return nil, err
	}
	rows := array(listing["data"])
	if len(rows) == 0 {
		return nil, failure("parser_changed")
	}
	container := object(object(rows[0])["card"])
	cards, ok := container["data"].([]any)
	if !ok {
		return nil, failure("parser_changed")
	}
	if len(cards) > 500 {
		return nil, failure("parser_changed")
	}
	result := []Job{}
	seen := map[string]bool{}
	for index, entry := range cards {
		card := object(entry)
		// The API defines cardorder; array order is used by upstream for older responses.
		cardIndex := index
		if value, ok := card["cardorder"]; ok {
			var valid bool
			cardIndex, valid = count(value)
			if !valid {
				return nil, failure("parser_changed")
			}
		}
		if cardIndex < 0 || cardIndex > 10000 {
			return nil, failure("parser_changed")
		}
		r.currentCard = &cardIndex
		page, err := r.cache.PageMobileChapterCard(classID, courseID, chapterID, cardIndex, cpi, 0, nil)
		if err != nil {
			return nil, r.coreError(err)
		}
		payload, err := taskData(page)
		if err != nil {
			return nil, err
		}
		for _, entry := range array(payload["attachments"]) {
			attachment := object(entry)
			if attachment == nil {
				return nil, failure("parser_changed")
			}
			job, keep, err := r.decodeJob(course, chapter, cardIndex, attachment, object(payload["defaults"]))
			if err != nil {
				return nil, err
			}
			if !keep {
				continue
			}
			if seen[job.ID] {
				continue
			}
			seen[job.ID] = true
			r.jobs[chapter.ID+":"+job.ID] = job
			result = append(result, job)
		}
	}
	if len(result) == 0 && chapter.JobCount > 0 {
		return nil, failure("jobs_missing")
	}
	return result, nil
}

func encoded(value any) map[string]any {
	raw, _ := json.Marshal(value)
	data, _ := parseObject(string(raw))
	return data
}
func title(property map[string]any, kind string) string {
	for _, key := range []string{"name", "title", "bookname"} {
		if value := field(property, key); value != "" {
			return value
		}
	}
	return kind
}

func (r *Runtime) decodeJob(course Course, chapter Chapter, card int, raw, defaults map[string]any) (Job, bool, error) {
	property := object(raw["property"])
	id := field(raw, "jobid")
	if id == "" {
		id = field(property, "jobid")
	}
	if id == "" {
		id = field(property, "_jobid")
	}
	if id == "" {
		if raw["job"] == true {
			return Job{}, false, failure("parser_changed")
		}
		return Job{}, false, nil
	}
	kind := field(raw, "type")
	if kind == "" {
		kind = field(property, "module")
	}
	switch kind {
	case "insertvideo":
		kind = "video"
	case "insertaudio":
		kind = "audio"
	case "insertdoc":
		kind = "document"
	case "insertreadv2", "insertbook":
		kind = "read"
	case "work":
		kind = "workid"
	}
	if property == nil {
		return Job{}, false, failure("parser_changed")
	}
	passed := raw["isPassed"] == true || (kind == "read" && property["read"] == true)
	job := Job{ID: id, ChapterID: chapter.ID, Kind: kind, Title: title(property, kind), Passed: passed, Card: card, Metadata: map[string]any{}, Defaults: defaults}
	_, explicitState := raw["isPassed"].(bool)
	_, readState := property["read"].(bool)
	if passed {
		return job, true, nil
	}
	if raw["job"] == nil && !explicitState && !(kind == "read" && readState) {
		job.Metadata["completion_unknown"] = true
		return job, true, nil
	}
	if raw["job"] == nil && explicitState {
		raw["job"] = true
	}
	// Normalize identifiers for upstream's typed attachment decoders.
	property["jobid"] = id
	property["_jobid"] = id
	if property["name"] == nil {
		property["name"] = job.Title
	}
	if property["title"] == nil {
		property["title"] = job.Title
	}
	if defaults["userid"] != nil {
		defaults["userid"] = text(defaults["userid"])
	}
	if defaults["fid"] != nil {
		defaults["fid"] = text(defaults["fid"])
	}
	data := map[string]any{"attachments": []any{raw}, "defaults": defaults}
	switch kind {
	case "video", "audio":
		objectID := field(property, "objectid")
		if objectID == "" {
			objectID = field(raw, "objectId")
		}
		p := yatori.PointVideoDto{CardIndex: card, CourseID: field(course, "courseId"), ClassID: field(course, "clazzId"), KnowledgeID: number(chapter.ID), Cpi: field(course, "cpi"), ObjectID: objectID, JobID: id, Title: job.Title, Type: ctype.Video, IsSet: true}
		if kind == "audio" {
			p.Type = ctype.InsertAudio
		}
		detected, err := p.AttachmentsDetection(data)
		if err != nil || !detected {
			return Job{}, false, failure("parser_changed")
		}
		if position, ok := raw["playTime"].(float64); ok && position >= 0 {
			job.Metadata["playTime"] = position
			p.PlayTime = int(position) / 1000
		}
		job.Metadata["video"] = encoded(p)
	case "document", "read":
		cardType := ctype.Document
		if kind == "read" {
			cardType = ctype.InsertReadV2
		}
		if field(property, "module") == "insertbook" {
			cardType = ctype.InsertBook
		}
		p := yatori.PointDocumentDto{CardIndex: card, CourseID: field(course, "courseId"), ClassID: field(course, "clazzId"), KnowledgeID: number(chapter.ID), Cpi: field(course, "cpi"), ObjectID: field(property, "objectid"), JobID: id, Title: job.Title, Type: cardType, IsSet: true}
		detected, err := p.AttachmentsDetection(data)
		if err != nil || !detected {
			return Job{}, false, failure("parser_changed")
		}
		if p.Jtoken == "" {
			return Job{}, false, failure("parser_changed")
		}
		job.Metadata["document"] = encoded(p)
	case "hyperlink":
		p := yatori.PointHyperlinkDto{CardIndex: card, CourseID: field(course, "courseId"), ClassID: field(course, "clazzId"), KnowledgeID: number(chapter.ID), JobID: id, Title: job.Title, Type: ctype.Hyperlink, IsSet: true}
		detected, err := p.AttachmentsDetection(data)
		if err != nil || !detected || p.Jtoken == "" {
			return Job{}, false, failure("parser_changed")
		}
		job.Metadata["hyperlink"] = encoded(p)
	case "workid":
		p := yatori.PointWorkDto{CardIndex: card, CourseID: field(course, "courseId"), ClassID: field(course, "clazzId"), KnowledgeID: number(chapter.ID), Cpi: field(course, "cpi"), JobID: id, WorkID: field(property, "workid"), Type: ctype.Work, IsSet: true}
		if p.WorkID == "" {
			p.WorkID = strings.TrimPrefix(id, "work-")
		}
		p.SchoolID = field(property, "schoolid")
		if p.SchoolID == "" {
			p.SchoolID = "0"
		}
		detected, err := p.AttachmentsDetection(data)
		if err != nil || !detected {
			return Job{}, false, failure("parser_changed")
		}
		job.Metadata["work"] = encoded(p)
	}
	return job, true, nil
}
