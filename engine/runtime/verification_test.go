package runtime

import (
	"net/http"
	"testing"
)

func TestChapterPaperReadsQuestionsWithInactiveVerificationResources(t *testing.T) {
	r := newTest(t)
	job := Job{ID: "work-51", ChapterID: "300", Kind: "workid", Metadata: map[string]any{"work": map[string]any{"CourseID": "100", "ClassID": "200", "WorkID": "51"}}}
	r.jobs["300:work-51"] = job
	page := chapterFixture() + inputs(map[string]string{"captchaCaptchaId": "inactive-challenge-nonce"}) +
		`<script>var prompts=["请输入验证码","人脸识别","安全验证","考试须知"];</script>` +
		`<div style="display: none"><input id="captcha"><input id="needFace" value="1">需要人脸识别</div>` +
		`<template>请输入验证码</template><div hidden>已截止，不能作答</div>`
	r.transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.Method != "GET" {
			t.Fatal("reading the paper attempted a write")
		}
		if req.URL.Path == "/knowledge/cards" {
			return reply(200, chapterCardFixture(false)), nil
		}
		return reply(200, page), nil
	})
	p, err := r.chapterPaper(testCourse, job)
	if err != nil || len(p.Questions) != 2 || p.chapterFields.Get("captchaCaptchaId") != "inactive-challenge-nonce" {
		t.Fatalf("question page was rejected or its form fields changed: %v", err)
	}
}

func TestActualVerificationRequirementsKeepSpecificReasons(t *testing.T) {
	for _, item := range []struct{ page, reason string }{
		{chapterFixture() + `<input type="hidden" id="needFace" value="1">`, "face"},
		{chapterFixture() + `<input name="captcha" placeholder="验证码">`, "captcha"},
		{chapterFixture() + `<p>请先完成人脸识别</p>`, "face"},
		{chapterFixture() + `<p>已截止，不能作答</p>`, "paper_closed"},
		{`<input id="captchaCaptchaId" value="required-nonce">`, "captcha"},
		{`<h1>考试须知</h1><p>请阅读并确认</p>`, "paper_notice"},
	} {
		_, err := paperDocument(item.page)
		if errorCode(err) != "manual_required" || manualReason(err) != item.reason {
			t.Fatalf("verification classification: want %s, got %v (%s)", item.reason, err, manualReason(err))
		}
	}
}

func TestQuestionTextAndHiddenMarkupAreSeparateFromVerification(t *testing.T) {
	page := chapterFixture() + `<p>待重做</p><div class="Py-mian1"><div class="workTextWrap">安全验证中的人脸识别是什么？请阅读考试须知。</div></div>`
	if _, err := paperDocument(page); err != nil {
		t.Fatalf("question content triggered verification: %v", err)
	}
}

func TestNetworkVerificationReasonsAndHiddenResources(t *testing.T) {
	for _, item := range []struct {
		body   string
		status int
		reason string
	}{
		{`<script>var prompt="请输入验证码";</script><div>课程列表</div>`, 200, ""},
		{`<div style="visibility: hidden">安全验证</div><div>课程列表</div>`, 200, ""},
		{`<p>请输入验证码</p>`, 200, "captcha"},
		{`{"needFace":true}`, 200, "face"},
		{`{"needCaptcha":1}`, 200, "captcha"},
		{`{"status":false,"msg":"请输入验证码"}`, 200, "captcha"},
		{`{}`, 429, "rate_limit"},
		{`{}`, 403, "access_restricted"},
	} {
		r := newTest(t)
		r.transport = roundTripFunc(func(*http.Request) (*http.Response, error) { return reply(item.status, item.body), nil })
		request, _ := http.NewRequest("GET", "https://mooc1.chaoxing.com/cards", nil)
		_, err := r.request(&http.Client{}, request)
		if (err == nil) != (item.reason == "") || manualReason(err) != item.reason {
			t.Fatalf("network verification: want %s, got %v (%s)", item.reason, err, manualReason(err))
		}
	}
}
