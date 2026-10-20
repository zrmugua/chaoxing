package runtime

// Paper forms follow the pinned Yatori api/xuexitong implementations.
// Hidden form values remain in this account's engine process.
import (
	"encoding/json"
	"net/url"
	"reflect"
	"regexp"
	"strconv"
	"strings"

	"github.com/PuerkitoBio/goquery"
	yatori "github.com/yatori-dev/yatori-go-core/api/xuexitong"
	"github.com/yatori-dev/yatori-go-core/que-core/aiq"
	"github.com/yatori-dev/yatori-go-core/utils"
)

type PaperQuestion struct {
	ID        string   `json:"id"`
	Title     string   `json:"title"`
	Type      string   `json:"type"`
	Code      string   `json:"code"`
	Options   []string `json:"options"`
	Blanks    int      `json:"blanks"`
	Supported bool     `json:"supported"`
}
type paper struct {
	ID            string          `json:"id"`
	Kind          string          `json:"kind"`
	Questions     []PaperQuestion `json:"questions"`
	fields        []map[string]string
	course        Course
	job           Job
	chapterFields url.Values
}

var questionTypes = map[string]string{"0": "单选题", "1": "多选题", "2": "填空题", "3": "判断题", "4": "简答题", "5": "名词解释", "6": "论述题"}
var safeID = regexp.MustCompile(`^[0-9]+$`)

func hiddenFields(doc *goquery.Document) map[string]string {
	fields := map[string]string{}
	doc.Find("input").Each(func(_ int, s *goquery.Selection) {
		value, _ := s.Attr("value")
		if id, ok := s.Attr("id"); ok {
			fields[strings.ToLower(id)] = value
		}
		if name, ok := s.Attr("name"); ok {
			fields[strings.ToLower(name)] = value
		}
	})
	return fields
}
func paperDocument(page string) (*goquery.Document, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(page))
	if err != nil {
		return nil, failure("parser_changed")
	}
	fields := hiddenFields(doc)
	for _, key := range []string{"captchacaptchaid", "needface", "needcaptcha", "needverify"} {
		if v := fields[key]; v != "" && v != "0" && v != "false" {
			return nil, failure("manual_required")
		}
	}
	for _, marker := range []string{"已截止，不能作答", "已过时效", "人脸识别", "考试须知", "待重考", "待重做"} {
		if strings.Contains(page, marker) {
			return nil, failure("manual_required")
		}
	}
	return doc, nil
}
func (r *Runtime) chapterPaper(course Course, supplied Job) (*paper, error) {
	job, err := r.canonical(supplied)
	if err != nil {
		return nil, err
	}
	if job.Kind != "workid" {
		return nil, failure("unsupported_job")
	}
	var point yatori.PointWorkDto
	if err = decodeDTO(job.Metadata["work"], &point); err != nil {
		return nil, err
	}
	page, err := r.cache.WorkFetchQuestion(&point, 0, nil)
	if err != nil {
		return nil, r.coreError(err)
	}
	doc, err := paperDocument(page)
	if err != nil {
		return nil, err
	}
	p := &paper{ID: job.ChapterID + ":" + job.ID, Kind: "chapter", course: course, job: job, Questions: []PaperQuestion{}, fields: []map[string]string{hiddenFields(doc)}}
	p.chapterFields = url.Values{}
	doc.Find("input[name]").Each(func(_ int, s *goquery.Selection) {
		typ, _ := s.Attr("type")
		if typ == "radio" || typ == "checkbox" {
			if _, ok := s.Attr("checked"); !ok {
				return
			}
		}
		name, _ := s.Attr("name")
		value, _ := s.Attr("value")
		p.chapterFields.Add(name, value)
	})
	doc.Find("textarea[name]").Each(func(_ int, s *goquery.Selection) { name, _ := s.Attr("name"); p.chapterFields.Set(name, s.Text()) })
	seen := map[string]bool{}
	for _, part := range utils.ParseQuestionSets(doc) {
		qdoc, e := goquery.NewDocumentFromReader(strings.NewReader(part.HTML))
		if e != nil {
			return nil, failure("parser_changed")
		}
		item := qdoc.Selection
		q := PaperQuestion{ID: part.ID, Title: strings.TrimSpace(item.Find(".Py-m1-title .workTextWrap").Text()), Options: []string{}}
		if q.Title == "" || !safeID.MatchString(q.ID) || seen[q.ID] {
			return nil, failure("parser_changed")
		}
		seen[q.ID] = true
		q.Type = strings.Trim(strings.TrimSpace(item.Find(".quesType").First().Text()), "[]【】")
		for code, name := range questionTypes {
			if q.Type == name {
				q.Code = code
			}
		}
		fields := hiddenFields(qdoc)
		if code := fields["answertype"+strings.ToLower(q.ID)]; code != "" {
			q.Code = code
			q.Type = questionTypes[code]
		}
		item.Find(".answerList li").Each(func(i int, s *goquery.Selection) {
			content := strings.TrimSpace(s.Find("cc").Text())
			if content == "" {
				content = strings.TrimSpace(s.Text())
				content = regexp.MustCompile(`^[A-N][.、．\s]+`).ReplaceAllString(content, "")
			}
			if content != "" {
				q.Options = append(q.Options, content)
			}
			// Upstream's submit API indexes canonical A..N. Stop on shuffled IDs.
			if canonical, ok := s.Find("em.choose-opt").Attr("id-param"); ok && canonical != "" && canonical != string(rune('A'+i)) {
				q.Type = "选项顺序需人工确认"
				q.Code = ""
			}
		})
		if q.Code == "2" {
			q.Blanks = item.Find(".blankItemName, .fillInBlank").Length()
			if q.Blanks == 0 {
				q.Blanks = number(fields["tiankongsize"+q.ID])
			}
		}
		q.Supported = q.Type != "" && (q.Code != "" && q.Code != "5")
		p.Questions = append(p.Questions, q)
	}
	if len(p.Questions) == 0 || len(p.Questions) > 200 {
		return nil, failure("parser_changed")
	}
	r.papers[p.ID] = p
	return p, nil
}
func reflectFields(target any, fields map[string]string) {
	v := reflect.ValueOf(target).Elem()
	t := v.Type()
	for i := 0; i < v.NumField(); i++ {
		if v.Field(i).Kind() == reflect.String {
			v.Field(i).SetString(fields[strings.ToLower(t.Field(i).Name)])
		}
	}
}
func parseMobileQuestion(page string) (PaperQuestion, map[string]string, error) {
	doc, err := paperDocument(page)
	if err != nil {
		return PaperQuestion{}, nil, err
	}
	f := hiddenFields(doc)
	q := PaperQuestion{ID: f["questionid"], Options: []string{}}
	q.Code = f["type"+q.ID]
	q.Type = questionTypes[q.Code]
	node := doc.Find("div.singleQuesId").First()
	if id, _ := node.Attr("data"); id != q.ID || !safeID.MatchString(q.ID) {
		return q, nil, failure("parser_changed")
	}
	title := node.Find("div.ans-cc.timuStyle.fontLabel.workWrap").First()
	if title.Length() == 0 {
		title = node.Find(".workWrap").First()
	}
	q.Title = strings.TrimSpace(title.Text())
	if q.Title == "" {
		return q, nil, failure("parser_changed")
	}
	node.Find("div.centerSpan").Each(func(i int, s *goquery.Selection) {
		letter, _ := s.Attr("id")
		if letter != string(rune('A'+i)) {
			q.Code = ""
		}
		q.Options = append(q.Options, strings.TrimSpace(s.Text()))
	})
	if q.Code == "3" {
		q.Options = []string{"正确", "错误"}
	}
	if q.Code == "2" {
		q.Blanks = node.Find(".blankItemName").Length()
	}
	q.Supported = q.Code != "" && q.Type != "" && q.Code != "5"
	f["score"] = f["score"+q.ID]
	f["questiontypestr"] = f["typename"+q.ID]
	f["questiontypecode"] = q.Code
	return q, f, nil
}
func acknowledged(raw string) bool {
	var data map[string]any
	if json.Unmarshal([]byte(raw), &data) != nil {
		return false
	}
	return data["status"] == true || data["result"] == true || data["success"] == true
}
func (r *Runtime) chaoxingAnswer(course Course, q PaperQuestion) (map[string]string, error) {
	if q.Title == "" || !q.Supported {
		return nil, failure("unsupported_job")
	}
	prompt := "请仅返回 JSON 字符串数组，每项为一个答案。选择题返回选项原文；判断题返回正确或错误；填空题按空顺序返回。题目：" + q.Title + " 选项：" + strings.Join(q.Options, "；")
	raw, err := r.cache.XueXiTongAIAggregation(field(course, "clazzId"), field(course, "courseId"), field(course, "cpi"), aiq.AIChatMessages{Messages: []aiq.Message{{Role: "user", Content: prompt}}})
	if err != nil {
		return nil, r.coreError(err)
	}
	if strings.TrimSpace(raw) == "" {
		return nil, failure("remote_error")
	}
	return map[string]string{"answer": raw}, nil
}
func paperCount(page string) int {
	doc, _ := goquery.NewDocumentFromReader(strings.NewReader(page))
	f := hiddenFields(doc)
	for _, key := range []string{"totalquestionnum", "questiontotal", "totalcount"} {
		if n, err := strconv.Atoi(f[key]); err == nil && n > 0 {
			return n
		}
	}
	match := regexp.MustCompile(`共(?:包含)?\s*(\d+)\s*(?:道题目|题)`).FindStringSubmatch(page)
	if len(match) > 1 {
		n, _ := strconv.Atoi(match[1])
		return n
	}
	return 0
}
func (r *Runtime) openAssessment(course Course, a Assessment) (*paper, error) {
	target, ok := r.assessmentsByID[a.Kind+":"+a.ID]
	if !ok || field(target.course, "courseId") != field(course, "courseId") || field(target.course, "clazzId") != field(course, "clazzId") {
		return nil, failure("parser_changed")
	}
	if target.status != "待做" && target.status != "未完成" && target.status != "未提交" && target.status != "待考试" && target.status != "进行中" {
		return nil, failure("manual_required")
	}
	f := target.params
	if f.Get("courseId") != field(course, "courseId") || f.Get("clazzId") != field(course, "clazzId") || f.Get("userId") != r.cache.UserID {
		return nil, failure("parser_changed")
	}
	for _, key := range []string{"taskrefId", "courseId", "clazzId", "userId", "enc_task"} {
		if f.Get(key) == "" {
			return nil, failure("parser_changed")
		}
	}
	var entry string
	var err error
	if a.Kind == "work" {
		entry, _, err = r.cache.PullWorkEnterInformHtmlApi(a.ID, f.Get("msgId"), f.Get("courseId"), f.Get("userId"), f.Get("clazzId"), f.Get("type"), f.Get("enc_task"), 0, nil)
	} else {
		entry, _, err = r.cache.PullExamEnterInformHtmlApi(a.ID, f.Get("msgId"), f.Get("courseId"), f.Get("userId"), f.Get("clazzId"), f.Get("type"), f.Get("enc_task"), 0, nil)
	}
	if err != nil {
		return nil, r.coreError(err)
	}
	doc, err := paperDocument(entry)
	if err != nil {
		return nil, err
	}
	values := hiddenFields(doc)
	total := paperCount(entry)
	cpi := field(course, "cpi")
	if values["cpi"] != "" {
		cpi = values["cpi"]
	}
	answerID := values["testuserrelationid"]
	enc := values["enc"]
	if a.Kind == "work" {
		// Yatori's work entry embeds the doHomeWork link in script text.
		for _, key := range []string{"workAnswerId", "enc", "cpi"} {
			match := regexp.MustCompile(key + `=([A-Za-z0-9_-]+)`).FindStringSubmatch(entry)
			if len(match) > 1 {
				switch key {
				case "workAnswerId":
					answerID = match[1]
				case "enc":
					enc = match[1]
				case "cpi":
					cpi = match[1]
				}
			}
		}
	}
	if answerID == "" || total < 1 || total > 200 {
		return nil, failure("parser_changed")
	}
	var page string
	if a.Kind == "work" {
		if enc == "" {
			return nil, failure("parser_changed")
		}
		page, err = r.cache.PullWorkPaperHtmlApi(f.Get("courseId"), f.Get("clazzId"), a.ID, "0", f.Get("msgId"), cpi, answerID, enc, "1", 0, nil)
	} else {
		if values["testpaperid"] == "" {
			return nil, failure("parser_changed")
		}
		page, err = r.cache.PullExamPaperHtmlApi(f.Get("courseId"), f.Get("clazzId"), values["testpaperid"], "0", answerID, cpi, "1", yatori.IMEI, "", "0", 0, nil)
	}
	if err != nil {
		return nil, r.coreError(err)
	}
	p := &paper{ID: a.Kind + ":" + a.ID, Kind: a.Kind, course: course, Questions: []PaperQuestion{}, fields: []map[string]string{}}
	seen := map[string]bool{}
	for i := 0; i < total; i++ {
		q, fields, parseErr := parseMobileQuestion(page)
		if parseErr != nil {
			return nil, parseErr
		}
		if seen[q.ID] {
			return nil, failure("parser_changed")
		}
		seen[q.ID] = true
		if fields["courseid"] != field(course, "courseId") || fields["classid"] != field(course, "clazzId") {
			return nil, failure("parser_changed")
		}
		if a.Kind == "work" {
			fields["workanswerid"] = answerID
			if fields["workid"] != a.ID {
				return nil, failure("parser_changed")
			}
		}
		p.Questions = append(p.Questions, q)
		p.fields = append(p.fields, fields)
		if i+1 < total {
			if a.Kind == "work" {
				page, err = r.cache.PullWorkQuestionApi(f.Get("courseId"), f.Get("clazzId"), a.ID, "0", f.Get("msgId"), cpi, answerID, fields["enc"], "1", i+1, 0, nil)
			} else {
				page, err = r.cache.PullExamQuestionApi(f.Get("courseId"), f.Get("clazzId"), values["testpaperid"], answerID, cpi, fields["encremaintime"], fields["enc"], fields["enclastupdatetime"], i+1)
			}
			if err != nil {
				return nil, r.coreError(err)
			}
		}
	}
	r.papers[p.ID] = p
	return p, nil
}
