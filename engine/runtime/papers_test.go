package runtime

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

func inputs(values map[string]string) string {
	result := ""
	for key, value := range values {
		result += fmt.Sprintf(`<input type="hidden" id="%s" name="%s" value="%s">`, key, key, value)
	}
	return result
}
func chapterFixture() string {
	return inputs(map[string]string{"answerId": "91", "workAnswerId": "92", "totalQuestionNum": "2", "enc_work": "fixture-token", "workRelationId": "51",
		"courseId": "100", "classId": "200", "answer11": "existing-answer"}) +
		`<div class="Py-mian1" data="10"><div class="Py-m1-title"><span class="quesType">[单选题]</span><span class="workTextWrap">Question one</span></div><ul class="answerList"><li><em class="choose-opt">A</em><cc>First</cc></li><li><em class="choose-opt">B</em><cc>Second</cc></li></ul></div>` +
		`<div class="Py-mian1" data="11"><div class="Py-m1-title"><span class="quesType">[简答题]</span><span class="workTextWrap">Question two</span></div></div>`
}

func chapterCardFixture(passed bool) string {
	payload := map[string]any{"attachments": []any{map[string]any{"type": "workid", "job": true, "jobid": "work-51", "isPassed": passed, "enc": "refreshed-enc",
		"property": map[string]any{"workid": "51", "jobid": "work-51", "title": "Chapter quiz", "name": "Chapter quiz"}}},
		"defaults": map[string]any{"userid": "42", "ktoken": "refreshed-ktoken"}}
	raw, _ := json.Marshal(payload)
	return "<script>window.AttachmentSetting=" + string(raw) + ";</script>"
}
func TestChapterPartialSavePreservesExistingAnswersAndCompletePolicy(t *testing.T) {
	for _, mode := range []string{"save", "submit", "complete"} {
		t.Run(mode, func(t *testing.T) {
			r := newTest(t)
			writes := 0
			job := Job{ID: "work-51", ChapterID: "300", Kind: "workid", Metadata: map[string]any{"work": map[string]any{"CourseID": "100", "ClassID": "200", "WorkID": "51"}}}
			r.jobs["300:work-51"] = job
			r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if req.URL.Path == "/knowledge/cards" {
					return reply(200, chapterCardFixture(false)), nil
				}
				if req.Method == "GET" {
					return reply(200, chapterFixture()), nil
				}
				writes++
				if req.URL.Path != "/mooc-ans/work/addStudentWorkNew" {
					t.Fatal("unexpected write endpoint")
				}
				if err := req.ParseMultipartForm(2_000_000); err != nil {
					t.Fatal(err)
				}
				if req.FormValue("answer10") != "B" || req.FormValue("answer11") != "existing-answer" || req.FormValue("courseId") != "100" {
					t.Fatal("answer fields were overwritten or incorrectly mapped")
				}
				expected := "1"
				if mode == "submit" {
					expected = ""
				}
				if req.FormValue("pyFlag") != expected {
					t.Fatal("wrong chapter save/submit semantics")
				}
				return reply(200, `{"status":true}`), nil
			})
			p, err := r.chapterPaper(testCourse, job)
			if err != nil {
				t.Fatal(err)
			}
			if len(p.Questions) != 2 || !p.Questions[0].Supported {
				t.Fatal("chapter parser missed questions")
			}
			result, err := r.saveAnswers(p.ID, map[string][]string{"10": {"Second"}}, mode != "save", mode == "complete")
			if err != nil || writes != 1 || result["submitted"] != (mode == "submit") || result["complete"] != false {
				t.Fatalf("invalid result: %v %v", result, err)
			}
		})
	}
}
func mobileFixture(kind string) string {
	return inputs(map[string]string{"questionId": "10", "type10": "0", "typeName10": "单选题", "courseId": "100", "classId": "200", "cpi": "400",
		"testPaperId": "51", "testUserRelationId": "91", "workId": "51", "enc": "fixture-enc", "encWork": "fixture-work-enc",
		"encRemainTime": "fixture-remaining", "encLastUpdateTime": "fixture-update", "userId": "42", "index": "0", "score10": "10"}) +
		`<div class="singleQuesId" data="10"><div class="ans-cc timuStyle fontLabel workWrap">Mobile question</div><div class="centerSpan" id="A">First</div><div class="centerSpan" id="B">Second</div></div>`
}
func TestYatoriMobilePaperUsesCanonicalEntryAndSaveSubmitAPIs(t *testing.T) {
	for _, kind := range []string{"work", "exam"} {
		for _, submit := range []bool{false, true} {
			t.Run(fmt.Sprintf("%s/%v", kind, submit), func(t *testing.T) {
				status := "待重考"
				if kind == "work" {
					status = "未交"
					if submit {
						status = "待重做"
					}
				}
				r := newTest(t)
				writes := 0
				r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
					if strings.Contains(req.URL.Path, "task-list") {
						return reply(200, `<ul class="nav"><li data="https://mooc1-api.chaoxing.com/android/mtaskmsgspecial?taskrefId=51&amp;courseId=100&amp;clazzId=200&amp;userId=42&amp;enc_task=fixture&amp;type=1&amp;msgId=0"><div><p>Paper</p><span>`+status+`</span></div></li></ul>`), nil
					}
					if strings.Contains(req.URL.Path, "mtaskmsgspecial") {
						return reply(200, inputs(map[string]string{"testPaperId": "51", "testUserRelationId": "91", "cpi": "400"})+`共包含 1 道题目<script>cpi=400&workAnswerId=91&enc=fixture-enc</script>`), nil
					}
					if req.Method == "GET" {
						return reply(200, mobileFixture(kind)), nil
					}
					writes++
					body, _ := io.ReadAll(req.Body)
					form, _ := url.ParseQuery(string(body))
					if form.Get("answer10") != "A" {
						t.Fatal("Yatori option mapping failed")
					}
					if form.Get("tempSave") != "" && form.Get("tempSave") != fmt.Sprint(!submit) {
						t.Fatal("wrong save/submit body")
					}
					if req.URL.Query().Get("tempSave") != fmt.Sprint(!submit) {
						t.Fatal("wrong save/submit query")
					}
					if form.Get("enc") == "" || form.Get("courseId") != "100" {
						t.Fatal("form metadata missing")
					}
					return reply(200, `{"status":true}`), nil
				})
				items, err := r.assessments(testCourse, kind == "work", kind == "exam")
				if err != nil {
					t.Fatal(err)
				}
				p, err := r.openAssessment(testCourse, items[0])
				if err != nil {
					t.Fatal(err)
				}
				raw, _ := json.Marshal(p)
				if strings.Contains(string(raw), "fixture-enc") {
					t.Fatal("hidden form token escaped engine")
				}
				result, err := r.saveAnswers(p.ID, map[string][]string{"10": {"First"}}, submit, true)
				if err != nil || writes != 1 || result["submitted"] != submit {
					t.Fatalf("submit: %v %v", result, err)
				}
			})
		}
	}
}
func TestPaperRefusesUnknownStructureAndManualVerification(t *testing.T) {
	for _, page := range []string{`<input id="captchaCaptchaId" value="fixture">`, `需要人脸识别`, `考试须知`} {
		if _, err := paperDocument(page); errorCode(err) != "manual_required" {
			t.Fatalf("manual challenge accepted: %v", err)
		}
	}
	if _, _, err := parseMobileQuestion(`<html>unexpected</html>`); errorCode(err) != "parser_changed" {
		t.Fatal("unknown page accepted")
	}
	r := newTest(t)
	if _, err := r.saveAnswers("unknown", map[string][]string{}, true, false); errorCode(err) != "parser_changed" {
		t.Fatal("unknown paper accepted")
	}
	if acknowledged(`{"message":"request sent"}`) || acknowledged(`<html>ok</html>`) {
		t.Fatal("unknown response accepted")
	}
}
