package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) {
	response, err := f(r)
	if response != nil && response.Request == nil {
		response.Request = r
	}
	return response, err
}
func reply(code int, body string) *http.Response {
	return &http.Response{StatusCode: code, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body))}
}
func newTest(t *testing.T) *Runtime {
	t.Helper()
	r, err := New(json.RawMessage(`{"credentials":{},"cookies":[{"name":"_uid","value":"42","domain":".chaoxing.com"}]}`))
	if err != nil {
		t.Fatal(err)
	}
	return r
}

var testCourse = Course{"courseId": "100", "clazzId": "200", "cpi": "400"}
var testChapter = Chapter{ID: "300", JobCount: 1}

func call(t *testing.T, r *Runtime, op string, args any) any {
	t.Helper()
	raw, _ := json.Marshal(args)
	value, err := r.Dispatch(op, raw)
	if err != nil {
		t.Fatalf("%s: %s", op, errorCode(err))
	}
	return value
}
func cardPage(kind string, passed bool) string {
	property := map[string]any{"jobid": "task-1", "_jobid": "task-1", "objectid": "object-fixture", "name": "Resource", "title": "Resource"}
	attachment := map[string]any{"type": kind, "job": true, "jobid": "task-1", "isPassed": passed, "property": property, "otherInfo": "nodeId_300-cpi_400", "jtoken": "fixture-jtoken", "mid": "fixture-mid", "playTime": 10000}
	data := map[string]any{"attachments": []any{attachment}, "defaults": map[string]any{"knowledgeid": 300, "fid": "1", "userid": "42", "reportTimeInterval": 5}}
	raw, _ := json.Marshal(data)
	return `<script>var mArg="";window.AttachmentSetting=` + string(raw) + `;</script>`
}

func TestYatoriLoginCourseChapterDocumentFlow(t *testing.T) {
	r := newTest(t)
	writes := 0
	requests := 0
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		requests++
		switch req.URL.Path {
		case "/fanyalogin":
			body, _ := io.ReadAll(req.Body)
			if strings.Contains(string(body), "private-fixture-password") {
				t.Fatal("password was not encrypted by Yatori")
			}
			response := reply(200, `{"status":true}`)
			response.Header.Add("Set-Cookie", "_uid=42; Domain=.chaoxing.com; Path=/")
			return response, nil
		case "/mycourse/backclazzdata":
			return reply(200, `{"result":1,"channelList":[{"cpi":400,"content":{"id":200,"course":{"data":[{"id":100,"name":"Course","teacherfactor":"Teacher"}]}}}]}`), nil
		case "/gas/clazz":
			return reply(200, `{"data":[{"course":{"data":[{"knowledge":{"data":[{"id":300,"name":"Chapter","jobcount":1,"indexorder":1,"status":"open"}]}}]}}]}`), nil
		case "/job/myjobsnodesmap":
			return reply(200, fmt.Sprintf(`{"300":{"totalcount":1,"finishcount":%d,"unfinishcount":%d,"openlock":1}}`, writes, 1-writes)), nil
		case "/gas/knowledge":
			return reply(200, `{"data":[{"id":300,"card":{"data":[{"cardorder":0}]}}]}`), nil
		case "/knowledge/cards":
			return reply(200, cardPage("document", writes > 0)), nil
		case "/ananas/job/document":
			if req.URL.Query().Get("jtoken") != "fixture-jtoken" {
				t.Fatal("Yatori document parameters missing")
			}
			writes++
			return reply(200, `{"status":true}`), nil
		}
		t.Fatalf("unexpected upstream request path: %s", req.URL.Path)
		return nil, nil
	})
	call(t, r, "login", map[string]any{"username": "fixture-user", "password": "private-fixture-password"})
	courses := call(t, r, "list_courses", map[string]any{}).([]Course)
	if len(courses) != 1 || field(courses[0], "courseId") != "100" {
		t.Fatal("course normalization failed")
	}
	chapters := call(t, r, "list_chapters", map[string]any{"course": testCourse}).([]Chapter)
	if chapters[0].Finished {
		t.Fatal("pending chapter marked finished")
	}
	jobs := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	if len(jobs) != 1 || jobs[0].Passed {
		t.Fatal("task parsing failed")
	}
	call(t, r, "execute", map[string]any{"course": testCourse, "job": jobs[0]})
	confirmed := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	if !confirmed[0].Passed {
		t.Fatal("server confirmation not retained")
	}
	chapters = call(t, r, "list_chapters", map[string]any{"course": testCourse}).([]Chapter)
	if !chapters[0].Finished || writes != 1 || requests < 8 {
		t.Fatal("readback contract failed")
	}
}

func TestVideoResumesFromServerPositionAtElapsedRealTime(t *testing.T) {
	r := newTest(t)
	now := time.Unix(1000, 0)
	r.now = func() time.Time { return now }
	r.wait = func(d time.Duration) error { now = now.Add(d); return nil }
	reports := []int{}
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		switch req.URL.Path {
		case "/gas/knowledge":
			return reply(200, `{"data":[{"card":{"data":[{"cardorder":0}]}}]}`), nil
		case "/knowledge/cards":
			return reply(200, cardPage("video", false)), nil
		case "/ananas/status/object-fixture":
			return reply(200, `{"status":"success","duration":12,"dtoken":"fixture-token"}`), nil
		case "/mooc-ans/multimedia/log/a/400/fixture-token":
			position, _ := strconv.Atoi(req.URL.Query().Get("playingTime"))
			reports = append(reports, position)
			ceiling := 10 + int(now.Sub(time.Unix(1000, 0)).Seconds())
			if position > ceiling {
				t.Fatal("reported time exceeded elapsed time")
			}
			return reply(200, `{"isPassed":false}`), nil
		}
		t.Fatalf("unexpected path: %s", req.URL.Path)
		return nil, nil
	})
	jobs := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	if number(jobs[0].Metadata["playTime"]) != 10000 {
		t.Fatal("server playTime was lost")
	}
	call(t, r, "execute", map[string]any{"course": testCourse, "job": jobs[0]})
	if len(reports) < 4 || reports[0] != 10 || reports[1] != 12 || reports[len(reports)-1] != 12 || now.Sub(time.Unix(1000, 0)) < 502*time.Second {
		t.Fatalf("unexpected reports: %v", reports)
	}
	if r.jobs["300:task-1"].Passed {
		t.Fatal("request success marked task complete")
	}
}

func TestGuardStopsVerificationAndUnsafeDestinations(t *testing.T) {
	for _, item := range []struct {
		endpoint, body, code string
		status               int
	}{
		{"https://mooc1.chaoxing.com/cards", "请输入验证码", "manual_required", 200},
		{"https://mooc1.chaoxing.com/cards", "", "manual_required", 403},
		{"https://mooc1.chaoxing.com/cards", "", "session_expired", 401},
		{"http://mooc1.chaoxing.com/cards", "", "blocked_destination", 200},
		{"https://external.invalid/cards", "", "blocked_destination", 200},
		{"https://mooc1.chaoxing.com/captcha/verify", "", "manual_required", 200},
	} {
		t.Run(item.code+item.endpoint+item.body, func(t *testing.T) {
			r := newTest(t)
			r.transport = roundTripFunc(func(*http.Request) (*http.Response, error) { return reply(item.status, item.body), nil })
			req, _ := http.NewRequest("GET", item.endpoint, nil)
			_, err := r.request(&http.Client{}, req)
			if err == nil || errorCode(err) != item.code {
				t.Fatalf("guard mismatch: %v", err)
			}
		})
	}
}

func TestGuardChecksRedirectBeforeCredentialsAreSent(t *testing.T) {
	r := newTest(t)
	requests := 0
	r.transport = roundTripFunc(func(*http.Request) (*http.Response, error) {
		requests++
		res := reply(302, "")
		res.Header.Set("Location", "https://external.invalid/")
		return res, nil
	})
	req, _ := http.NewRequest("GET", "https://mooc1.chaoxing.com/cards", nil)
	req.Header.Set("Cookie", "fixture-private-cookie")
	_, err := r.request(&http.Client{}, req)
	if errorCode(err) != "blocked_destination" || requests != 1 {
		t.Fatal("redirect boundary failed")
	}
}

func TestTaskPageRequiresStructuredPayload(t *testing.T) {
	for _, page := range []string{"", "<html>unexpected</html>", `mArg={broken};`, `mArg={"attachments":null,"defaults":{}};`} {
		if _, err := taskData(page); err == nil {
			t.Fatal("unknown page accepted")
		}
	}
	data, err := taskData(cardPage("document", false))
	if err != nil || len(array(data["attachments"])) != 1 {
		t.Fatal("page template parsing failed")
	}
}

func TestReadTimeoutContextPropagates(t *testing.T) {
	r := newTest(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r.ctx = ctx
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) { return nil, req.Context().Err() })
	req, _ := http.NewRequest("GET", "https://mooc1.chaoxing.com/cards", nil)
	if _, err := r.request(&http.Client{}, req); err == nil {
		t.Fatal("cancellation lost")
	}
}

func TestUnsafeCookieDomainsAreFiltered(t *testing.T) {
	r, err := New(json.RawMessage(`{"credentials":{},"cookies":[{"name":"x","value":"private-cookie","domain":"external.invalid"}]}`))
	if err != nil {
		t.Fatal(err)
	}
	cookies := call(t, r, "export_cookies", map[string]any{}).([]Cookie)
	if len(cookies) != 0 {
		t.Fatal("foreign cookie imported")
	}
	if _, err := url.Parse("https://mooc1.chaoxing.com/"); err != nil {
		t.Fatal(err)
	}
}

func TestQuizPreviewUsesYatoriQuestionParserAndReadOnlyRequest(t *testing.T) {
	r := newTest(t)
	raw := map[string]any{"type": "workid", "jobid": "work-500", "job": true, "isPassed": false, "enc": "fixture-enc", "property": map[string]any{"workid": "500", "jobid": "work-500", "title": "Quiz"}}
	defaults := map[string]any{"ktoken": "fixture-token", "userid": "42", "knowledgeid": 300}
	job, keep, err := r.decodeJob(testCourse, testChapter, 0, raw, defaults)
	if err != nil || !keep {
		t.Fatal("Yatori work DTO was not decoded")
	}
	r.jobs["300:work-500"] = job
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.Method == "GET" && req.URL.Path == "/knowledge/cards" {
			payload, _ := json.Marshal(map[string]any{"attachments": []any{raw}, "defaults": defaults})
			return reply(200, "<script>window.AttachmentSetting="+string(payload)+";</script>"), nil
		}
		if req.Method != "GET" || req.URL.Path != "/android/mworkspecial" || req.URL.Query().Get("workid") != "500" {
			t.Fatal("quiz preview used unexpected request")
		}
		return reply(200, `<div class="Py-mian1" data="10"><div class="Py-m1-title"><span class="quesType">[单选题]</span><span class="workTextWrap">Question text</span></div><ul class="answerList"><li><em class="choose-opt">A</em><cc>First</cc></li><li><em class="choose-opt">B</em><cc>Second</cc></li></ul></div>`), nil
	})
	questions := call(t, r, "questions", map[string]any{"course": testCourse, "job": job}).([]map[string]any)
	if len(questions) != 1 || questions[0]["id"] != "10" || questions[0]["title"] != "Question text" || len(questions[0]["options"].([]string)) != 2 {
		t.Fatal("question preview shape mismatch")
	}
}

func TestUnknownTaskStateCannotBeOverriddenByCaller(t *testing.T) {
	r := newTest(t)
	raw := map[string]any{"type": "document", "jobid": "unknown", "property": map[string]any{"name": "Unknown"}}
	job, keep, err := r.decodeJob(testCourse, testChapter, 0, raw, map[string]any{})
	if err != nil || !keep || job.Passed || job.Metadata["completion_unknown"] != true {
		t.Fatal("unknown completion was lost")
	}
	r.jobs["300:unknown"] = job
	r.transport = roundTripFunc(func(*http.Request) (*http.Response, error) { t.Fatal("unknown task was executed"); return nil, nil })
	forged := job
	forged.Metadata = map[string]any{}
	args, _ := json.Marshal(map[string]any{"course": testCourse, "job": forged})
	if _, err := r.Dispatch("execute", args); errorCode(err) != "job_state_unknown" {
		t.Fatal("canonical task state was bypassed")
	}
}

func TestIdenticalPagePayloadAliasesAreAccepted(t *testing.T) {
	page := cardPage("document", false)
	data, err := taskData(page)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(data)
	if _, err := taskData(page + "mArg=" + string(raw) + ";"); err != nil {
		t.Fatal("identical aliases rejected")
	}
}

func TestNumericAccountCookieTakesPriority(t *testing.T) {
	for _, cookies := range []string{
		`[{"name":"_uid","value":"42","domain":".chaoxing.com"},{"name":"UID","value":"other-id","domain":".chaoxing.com"}]`,
		`[{"name":"UID","value":"other-id","domain":".chaoxing.com"},{"name":"_uid","value":"42","domain":".chaoxing.com"}]`,
	} {
		r, err := New(json.RawMessage(`{"credentials":{},"cookies":` + cookies + `}`))
		if err != nil || r.cache.UserID != "42" {
			t.Fatal("account identifier depends on cookie order")
		}
	}
}

func TestChapterCompletionRequiresValidServerCounts(t *testing.T) {
	for _, item := range []struct {
		counts   string
		complete bool
	}{
		{`"totalcount":1,"finishcount":1,"unfinishcount":0`, true},
		{`"totalcount":"1","finishcount":"1","unfinishcount":"0"`, true},
		{`"totalcount":1,"finishcount":1`, false},
		{`"totalcount":1,"finishcount":1,"unfinishcount":"invalid"`, false},
		{`"totalcount":1,"finishcount":1,"unfinishcount":0.5`, false},
		{`"totalcount":0,"finishcount":0,"unfinishcount":0`, false},
		{`"totalcount":1,"finishcount":0,"unfinishcount":0`, false},
	} {
		t.Run(item.counts, func(t *testing.T) {
			r := newTest(t)
			r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if req.URL.Path == "/gas/clazz" {
					return reply(200, `{"data":[{"course":{"data":[{"knowledge":{"data":[{"id":300,"name":"Chapter","jobcount":1}]}}]}}]}`), nil
				}
				return reply(200, `{"300":{`+item.counts+`}}`), nil
			})
			chapters := call(t, r, "list_chapters", map[string]any{"course": testCourse}).([]Chapter)
			if len(chapters) != 1 || chapters[0].Finished != item.complete {
				t.Fatal("invalid completion evidence accepted")
			}
		})
	}
}

func TestOnlyExplicitlyEmptyParentHeadingsAreFiltered(t *testing.T) {
	for _, item := range []struct {
		count    string
		expected int
	}{
		{`0`, 1}, {`"0"`, 1}, {`null`, 2}, {`"invalid"`, 2}, {`1`, 2},
	} {
		t.Run(item.count, func(t *testing.T) {
			r := newTest(t)
			r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if req.URL.Path == "/gas/clazz" {
					return reply(200, `{"data":[{"course":{"data":[{"knowledge":{"data":[{"id":299,"name":"Parent","jobcount":`+item.count+`},{"id":300,"parentnodeid":299,"name":"Child","jobcount":1}]}}]}}]}`), nil
				}
				return reply(200, `{}`), nil
			})
			chapters := call(t, r, "list_chapters", map[string]any{"course": testCourse}).([]Chapter)
			if len(chapters) != item.expected {
				t.Fatal("unknown parent task count was discarded")
			}
		})
	}
}

func TestAudioUsesYatoriAudioEndpointAndRealElapsedTime(t *testing.T) {
	r := newTest(t)
	now := time.Unix(1000, 0)
	r.now = func() time.Time { return now }
	r.wait = func(d time.Duration) error { now = now.Add(d); return nil }
	reports := []int{}
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		switch req.URL.Path {
		case "/gas/knowledge":
			return reply(200, `{"data":[{"card":{"data":[{"cardorder":0}]}}]}`), nil
		case "/knowledge/cards":
			return reply(200, cardPage("insertaudio", false)), nil
		case "/ananas/status/object-fixture":
			return reply(200, `{"status":"success","duration":12,"dtoken":"fixture-token"}`), nil
		case "/mooc-ans/multimedia/log":
			if req.URL.Query().Get("dtype") != "Audio" {
				t.Fatal("audio endpoint type missing")
			}
			position, _ := strconv.Atoi(req.URL.Query().Get("playingTime"))
			reports = append(reports, position)
			if position > 10+int(now.Sub(time.Unix(1000, 0)).Seconds()) {
				t.Fatal("audio position exceeded elapsed time")
			}
			return reply(200, `{"isPassed":false}`), nil
		}
		t.Fatalf("unexpected audio request: %s", req.URL.Path)
		return nil, nil
	})
	jobs := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	if jobs[0].Kind != "audio" {
		t.Fatal("audio task kind lost")
	}
	call(t, r, "execute", map[string]any{"course": testCourse, "job": jobs[0]})
	if len(reports) < 4 || reports[0] != 10 || reports[len(reports)-1] != 12 || now.Sub(time.Unix(1000, 0)) < 502*time.Second {
		t.Fatal("audio resume failed")
	}
	if r.jobs["300:task-1"].Passed {
		t.Fatal("audio request inferred completion")
	}
}

func TestHyperlinkUsesYatoriDTOAndNeedsReadback(t *testing.T) {
	r := newTest(t)
	writes := 0
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		switch req.URL.Path {
		case "/gas/knowledge":
			return reply(200, `{"data":[{"card":{"data":[{"cardorder":0}]}}]}`), nil
		case "/knowledge/cards":
			return reply(200, cardPage("hyperlink", writes > 0)), nil
		case "/ananas/job/hyperlink":
			if req.URL.Query().Get("jtoken") != "fixture-jtoken" || req.URL.Query().Get("jobid") != "task-1" {
				t.Fatal("hyperlink DTO fields lost")
			}
			writes++
			return reply(200, `{"status":true}`), nil
		}
		t.Fatalf("unexpected hyperlink request: %s", req.URL.Path)
		return nil, nil
	})
	jobs := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	call(t, r, "execute", map[string]any{"course": testCourse, "job": jobs[0]})
	if r.jobs["300:task-1"].Passed {
		t.Fatal("hyperlink request inferred completion")
	}
	fresh := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	if !fresh[0].Passed || writes != 1 {
		t.Fatal("hyperlink readback failed")
	}
}

func TestAssessmentListsUseReadOnlyYatoriEndpoints(t *testing.T) {
	r := newTest(t)
	paths := map[string]bool{}
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.Method != "GET" {
			t.Fatal("list operation changed remote state")
		}
		if req.URL.Path != "/work/task-list" && req.URL.Path != "/mooc-ans/exam/phone/task-list" {
			t.Fatalf("unexpected endpoint %s", req.URL.Path)
		}
		paths[req.URL.Path] = true
		return reply(200, `<ul class="nav"><li data="/entry?taskrefId=501&amp;enc_task=private-fixture"><div><p>Assessment</p><span>未开始</span><span>2 days</span></div></li></ul>`), nil
	})
	items := call(t, r, "list_assessments", map[string]any{"course": testCourse, "work": true, "exam": true}).([]Assessment)
	if len(items) != 2 || len(paths) != 2 || items[0].ID != "501" || items[1].Kind != "exam" {
		t.Fatal("assessment normalization failed")
	}
	raw, _ := json.Marshal(items)
	if strings.Contains(string(raw), "private-fixture") {
		t.Fatal("assessment list exposed entry token")
	}
	for _, page := range []string{"<html>changed</html>", `<ul class="nav"><li>Unknown</li></ul>`, `<ul class="nav"><li><div><p>Unknown ID</p></div></li></ul>`, `<ul class="nav"></ul>`} {
		if _, err := assessmentList(page, "work"); err == nil {
			t.Fatal("unknown assessment page accepted")
		}
	}
	if items, err := assessmentList(`<ul class="nav"></ul><p>暂无作业</p>`, "work"); err != nil || len(items) != 0 {
		t.Fatal("explicit empty work list rejected")
	}
	if _, err := assessmentList(`<ul class="nav"></ul><p>暂无作业</p>`, "exam"); err == nil {
		t.Fatal("work placeholder inferred empty exam list")
	}
}

func TestMobileVideoSettingReachesMobileYatoriAPI(t *testing.T) {
	r, err := New(json.RawMessage(`{"credentials":{"media_client":"mobile"},"cookies":[{"name":"_uid","value":"42","domain":".chaoxing.com"}]}`))
	if err != nil {
		t.Fatal(err)
	}
	sent := false
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		switch req.URL.Path {
		case "/gas/knowledge":
			return reply(200, `{"data":[{"card":{"data":[{"cardorder":0}]}}]}`), nil
		case "/knowledge/cards":
			return reply(200, cardPage("video", false)), nil
		case "/ananas/status/object-fixture":
			return reply(200, `{"status":"success","duration":12,"dtoken":"fixture-token"}`), nil
		case "/mooc-ans/multimedia/log/a/400/fixture-token":
			if req.URL.Hostname() != "mooc1.chaoxing.com" || req.URL.Query().Get("dtype") != "Video" {
				t.Fatal("mobile video API was not selected")
			}
			sent = true
			return reply(200, `{"isPassed":true}`), nil
		}
		t.Fatalf("unexpected request %s", req.URL.Path)
		return nil, nil
	})
	jobs := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	call(t, r, "execute", map[string]any{"course": testCourse, "job": jobs[0]})
	if !sent {
		t.Fatal("mobile setting did not reach execution")
	}
}
