package runtime

// Form contract: pinned Yatori XueXiTongChapterTestApi.WorkNewSubmitAnswer.
// Preserve existing answer fields when a provider cannot resolve a question.
import (
	"bytes"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

func (r *Runtime) submitChapter(p *paper, answers map[string][]string, submit bool) error {
	fields := p.fields[0]
	for _, key := range []string{"answerid", "workanswerid", "totalquestionnum", "enc_work", "workrelationid"} {
		if fields[key] == "" {
			return failure("parser_changed")
		}
	}
	if number(fields["totalquestionnum"]) != len(p.Questions) || p.chapterFields == nil {
		return failure("parser_changed")
	}
	values := url.Values{}
	for key, items := range p.chapterFields {
		values[key] = append([]string{}, items...)
	}
	values.Set("pyFlag", "1")
	if submit {
		values.Set("pyFlag", "")
	}
	for key, value := range map[string]string{"courseId": field(p.course, "courseId"), "classId": field(p.course, "clazzId"),
		"cpi": field(p.course, "cpi"), "knowledgeid": p.job.ChapterID, "jobid": p.job.ID, "userId": r.cache.UserID} {
		values.Set(key, value)
	}
	ids := []string{}
	for _, q := range p.Questions {
		ids = append(ids, q.ID)
		a := answers[q.ID]
		if len(a) == 0 {
			continue
		}
		values.Set("answertype"+q.ID, q.Code)
		switch q.Code {
		case "0", "1":
			letters := ""
			for i, option := range q.Options {
				for _, answer := range a {
					if option == answer {
						letters += string(rune('A' + i))
						break
					}
				}
			}
			values.Set("answer"+q.ID, letters)
		case "3":
			values.Set("answer"+q.ID, strconv.FormatBool(a[0] == "正确"))
		case "2":
			for i, s := range a {
				values.Set("answer"+q.ID+strconv.Itoa(i+1), s)
			}
			values.Set("tiankongsize"+q.ID, strconv.Itoa(q.Blanks))
		case "4", "5", "6":
			values.Set("answer"+q.ID, a[0])
		default:
			return failure("manual_required")
		}
	}
	values.Set("answerwqbid", strings.Join(ids, ",")+",")
	payload := &bytes.Buffer{}
	writer := multipart.NewWriter(payload)
	for key, items := range values {
		for _, value := range items {
			if err := writer.WriteField(key, value); err != nil {
				return err
			}
		}
	}
	if err := writer.Close(); err != nil {
		return err
	}
	query := url.Values{"_classId": {field(p.course, "clazzId")}, "courseid": {field(p.course, "courseId")}, "token": {fields["enc_work"]},
		"totalQuestionNum": {fields["totalquestionnum"]}, "ua": {"pc"}, "formType": {"post"}, "saveStatus": {"1"}, "version": {"1"}, "tempsave": {"1"}}
	request, err := http.NewRequest("POST", "https://mooc1.chaoxing.com/mooc-ans/work/addStudentWorkNew?"+query.Encode(), payload)
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", writer.FormDataContentType())
	request.Header.Set("User-Agent", "Mozilla/5.0")
	for _, cookie := range r.cache.GetCookies() {
		request.AddCookie(cookie)
	}
	response, err := r.request(&http.Client{}, request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil {
		return err
	}
	if !acknowledged(string(raw)) {
		return failure("remote_error")
	}
	return nil
}
