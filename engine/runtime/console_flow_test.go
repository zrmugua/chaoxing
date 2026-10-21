package runtime

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"testing"
	"time"

	lg "github.com/yatori-dev/yatori-go-core/utils/log"
)

func chapterTestJob(r *Runtime) Job {
	job := Job{ID: "work-51", ChapterID: "300", Kind: "workid", Card: 1, Metadata: map[string]any{"work": map[string]any{"WorkID": "51", "Enc": "stale-enc"}}}
	r.jobs["300:work-51"] = job
	return job
}

func TestConsoleRefreshAlternateReadAndShuffledOptionSave(t *testing.T) {
	r := newTest(t)
	job := chapterTestJob(r)
	order := []string{}
	page := strings.ReplaceAll(chapterFixture(), `<em class="choose-opt">A</em>`, `<em class="choose-opt" id-param="B">A</em>`)
	page = strings.ReplaceAll(page, `<em class="choose-opt">B</em>`, `<em class="choose-opt" id-param="A">B</em>`)
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		order = append(order, req.URL.Path)
		switch req.URL.Path {
		case "/knowledge/cards":
			if req.URL.Query().Get("num") != "1" {
				t.Fatal("wrong task card refreshed")
			}
			return reply(200, chapterCardFixture(false)), nil
		case "/android/mworkspecial":
			if req.URL.Query().Get("enc") != "refreshed-enc" || req.URL.Query().Get("ktoken") != "refreshed-ktoken" {
				t.Fatal("stale work parameters used")
			}
			return reply(200, `<p class="blankTips">无效的权限,code=2</p>`), nil
		case "/mooc-ans/work/phone/work":
			return reply(200, page), nil
		case "/mooc-ans/work/addStudentWorkNew":
			if err := req.ParseMultipartForm(2_000_000); err != nil {
				t.Fatal(err)
			}
			if req.FormValue("answer10") != "B" || req.FormValue("answer11") != "existing-answer" || req.FormValue("pyFlag") != "1" {
				t.Fatal("canonical option mapping or existing answer was lost")
			}
			return reply(200, `{"status":true}`), nil
		}
		t.Fatalf("unexpected request: %s", req.URL.Path)
		return nil, nil
	})
	p, err := r.chapterPaper(testCourse, job)
	if err != nil {
		t.Fatal(err)
	}
	if !p.Questions[0].Supported || p.Questions[0].Options[0] != "Second" {
		t.Fatal("upstream option identifiers were discarded")
	}
	if _, err := r.saveAnswers(p.ID, map[string][]string{"10": {"First"}}, false, false); err != nil {
		t.Fatal(err)
	}
	if len(order) != 4 || order[0] != "/knowledge/cards" || order[2] != "/mooc-ans/work/phone/work" {
		t.Fatal("Console reading sequence changed")
	}
}

func TestConsoleRefreshRecognizesAlreadyCompletedPaper(t *testing.T) {
	r := newTest(t)
	job := chapterTestJob(r)
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.URL.Path != "/knowledge/cards" || req.Method != "GET" {
			t.Fatal("completed paper was reopened")
		}
		return reply(200, chapterCardFixture(true)), nil
	})
	p, err := r.chapterPaper(testCourse, job)
	if err != nil || !p.Passed || len(p.Questions) != 0 {
		t.Fatal("completed work was not skipped")
	}
}

func TestConsoleActualVerificationStopsWithoutAlternateRead(t *testing.T) {
	r := newTest(t)
	job := chapterTestJob(r)
	reads := 0
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		reads++
		if req.URL.Path == "/knowledge/cards" {
			return reply(200, chapterCardFixture(false)), nil
		}
		if req.URL.Path != "/android/mworkspecial" {
			t.Fatal("active verification triggered another request")
		}
		return reply(200, `<input name="captcha"><p>请输入验证码</p>`), nil
	})
	_, err := r.chapterPaper(testCourse, job)
	if errorCode(err) != "manual_required" || manualReason(err) != "captcha" || reads != 2 {
		t.Fatalf("verification classification changed: %v", err)
	}
}

func TestConsoleMediaWaitsForDelayedServerConfirmation(t *testing.T) {
	r := newTest(t)
	now, start := time.Unix(1000, 0), time.Unix(1000, 0)
	r.now = func() time.Time { return now }
	r.wait = func(duration time.Duration) error { now = now.Add(duration); return nil }
	reports := 0
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		switch req.URL.Path {
		case "/gas/knowledge":
			return reply(200, `{"data":[{"card":{"data":[{"cardorder":0}]}}]}`), nil
		case "/knowledge/cards":
			return reply(200, cardPage("video", false)), nil
		case "/ananas/status/object-fixture":
			return reply(200, `{"status":"success","duration":12,"dtoken":"fixture-token"}`), nil
		case "/mooc-ans/multimedia/log/a/400/fixture-token":
			reports++
			position, _ := strconv.Atoi(req.URL.Query().Get("playingTime"))
			if position > 10+int(now.Sub(start).Seconds()) {
				t.Fatal("media report advanced beyond elapsed time")
			}
			return reply(200, `{"isPassed":`+strconv.FormatBool(reports >= 4)+`}`), nil
		}
		t.Fatalf("unexpected request: %s", req.URL.Path)
		return nil, nil
	})
	jobs := call(t, r, "list_jobs", map[string]any{"course": testCourse, "chapter": testChapter}).([]Job)
	call(t, r, "execute", map[string]any{"course": testCourse, "job": jobs[0]})
	if reports != 4 || now.Sub(start) != 12*time.Second {
		t.Fatal("delayed completion window was not respected")
	}
}

func TestConsoleWaitCanBeCancelled(t *testing.T) {
	r := newTest(t)
	r.wait = func(time.Duration) error { return context.Canceled }
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.URL.Path == "/knowledge/cards" {
			return reply(200, cardPage("video", false)), nil
		}
		if strings.HasPrefix(req.URL.Path, "/ananas/status/") {
			return reply(200, `{"status":"success","duration":12,"dtoken":"fixture-token"}`), nil
		}
		return reply(200, `{"isPassed":false}`), nil
	})
	job, _, err := r.decodeJob(testCourse, testChapter, 0, objectFromCard(t), map[string]any{"userid": "42", "fid": "1"})
	if err != nil {
		t.Fatal(err)
	}
	r.jobs["300:task-1"] = job
	if err := r.execute(testCourse, job); !errors.Is(err, context.Canceled) {
		t.Fatal("Console wait ignored cancellation")
	}
}

func objectFromCard(t *testing.T) map[string]any {
	t.Helper()
	payload, err := taskData(cardPage("video", false))
	if err != nil {
		t.Fatal(err)
	}
	return object(array(payload["attachments"])[0])
}

func TestCoreDebugSettingReachesConsoleLogger(t *testing.T) {
	_, err := New(json.RawMessage(`{"credentials":{"log_level":"debug"}}`))
	if err != nil || lg.NOWLOGLEVEL != lg.DEBUG {
		t.Fatal("debug setting did not initialize the Core logger")
	}
	defer lg.LogInit(lg.INFO, false, 0, "")
	var lines []string
	capture, err := captureConsole(func(line string) { lines = append(lines, line) })
	if err != nil {
		t.Fatal(err)
	}
	lg.Print(lg.DEBUG, "Core debug output")
	capture.flush()
	capture.close()
	if len(lines) != 1 || !strings.Contains(lines[0], "Core debug output") {
		t.Fatal("Core debug output was unavailable")
	}
}
