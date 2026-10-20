import json

import pytest
import yaml

from backend.app.answering import normalize_answer
from backend.app.learning import DEFAULT_RULES
from backend.app.services import PlatformService
from backend.tests.test_platform import platform, add_account, add_course, RecordingAdapter, study_setup


def test_yatori_yaml_round_trip_preserves_rules_and_hides_credentials(platform):
    _, app, client = platform
    account = add_account(client)
    rules = DEFAULT_RULES | {"answer_mode": "chaoxing_ai", "submit_mode": "complete", "video_mode": "multi_node",
                             "work": True, "exam": True, "include_courses": ["100"]}
    assert client.put(f"/api/accounts/{account}/study-settings", json=rules).status_code == 200
    assert client.put(f"/api/accounts/{account}/preferences", json={"inform_emails": ["a@example.com"],
                      "proxy_url": "http://fixture-user:fixture-secret@127.0.0.1:7890"}).status_code == 200
    public = client.get("/api/configuration/export").text
    assert "account-canary-secret" not in public and "fixture-secret" not in public
    exported = client.get("/api/configuration/export?include_secrets=true").text
    data = yaml.safe_load(exported)
    assert data["users"][0]["coursesCustom"]["autoExam"] == 3
    assert data["users"][0]["coursesCustom"]["examAutoSubmit"] == 2
    assert "account-canary-secret" in exported
    client.put(f"/api/accounts/{account}/study-settings", json=DEFAULT_RULES)
    assert client.post("/api/configuration/import", json={"text": exported}).status_code == 200
    service = PlatformService(app.state.db, app.state.vault)
    assert service.study_settings(account) == rules
    assert service.account_preferences(account, True)["inform_emails"] == ["a@example.com"]
    stored = app.state.db.one("SELECT payload FROM account_preferences")["payload"]
    assert "fixture-secret" not in stored and "a@example.com" not in stored


def test_original_generator_import_creates_accounts_atomically(platform):
    _, app, client = platform
    users = [{"accountType": "XUEXITONG", "account": "fixture-one", "password": "fixture-password",
              "remarkName": "账号一", "informEmails": [], "coursesCustom": {
                  "videoModel": 2, "autoExam": 2, "examAutoSubmit": 1,
                  "cxNode": 3, "cxChapterTestSw": 1, "cxWorkSw": 1, "cxExamSw": 0,
                  "includeCourses": [], "excludeCourses": ["不学习的课程"]}}]
    result = client.post("/api/configuration/import", json={"text": yaml.safe_dump({"users": users})})
    assert result.status_code == 200 and result.json()["accounts"] == 1
    service = PlatformService(app.state.db, app.state.vault)
    account = app.state.db.one("SELECT id FROM accounts")["id"]
    assert service.study_settings(account)["answer_mode"] == "question_bank"
    assert service.study_settings(account)["work"] and not service.study_settings(account)["exam"]
    users.append(users[0] | {"account": "fixture-two", "coursesCustom": {"autoExam": 99}})
    result = client.post("/api/configuration/import", json={"text": yaml.safe_dump({"users": users})})
    assert result.status_code == 422 and len(client.get("/api/accounts").json()) == 1


@pytest.mark.parametrize("text", ["users: [", "users: &a [*a]", "users: [{accountType: OTHER}]", "users: [null]"])
def test_import_rejects_invalid_configuration_without_leaking_content(platform, text):
    _, _, client = platform
    result = client.post("/api/configuration/import", json={"text": text})
    assert result.status_code == 422
    assert text not in result.text


def test_plan_fingerprint_rejects_changed_rules(platform):
    _, app, client = platform
    account = add_account(client)
    course = add_course(app, account)
    plan = client.get(f"/api/accounts/{account}/study-plan").json()
    assert plan["count"] == 1 and not plan["will_submit"]
    assert client.put(f"/api/accounts/{account}/study-settings", json=DEFAULT_RULES | {"video_mode": "off"}).status_code == 200
    assert client.post(f"/api/accounts/{account}/study", json={"fingerprint": plan["fingerprint"]}).status_code == 409
    assert client.post(f"/api/courses/{course}/study", json={"fingerprint": plan["fingerprint"]}).status_code == 409
    assert client.get("/api/tasks").json() == []


def test_task_creation_keeps_the_reviewed_plan_snapshot(platform):
    _, app, client = platform
    account = add_account(client)
    add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    plan = service.study_plan(account)
    client.put(f"/api/accounts/{account}/study-settings", json=DEFAULT_RULES | {"video_mode": "off"})
    queued = service.queue_courses(account, plan)
    assert len(queued["tasks"]) == 1
    assert json.loads(queued["tasks"][0]["checkpoint"])["options"]["video_mode"] == "normal"


@pytest.mark.parametrize("code,options,raw,expected", [
    ("0", ["first", "second"], '["B"]', ["second"]),
    ("0", ["first", "second"], 'probably B', []),
    ("0", ["first", "second"], '["first", "second"]', []),
    ("1", ["first", "second"], 'AB', ["first", "second"]),
    ("1", ["first", "second"], '["first", "unknown"]', []),
    ("3", [], '["false"]', ["错误"]),
    ("3", [], '["不确定"]', []),
    ("2", [], '["one", "two"]', ["one", "two"]),
    ("2", [], '["one"]', []),
])
def test_answer_normalization_is_exact(code, options, raw, expected):
    assert normalize_answer(raw, {"supported": True, "code": code, "options": options, "blanks": 2}) == expected


def test_chapter_save_is_not_course_completion_and_never_replays(platform, monkeypatch):
    from backend.app.adapters.contracts import Job
    _, _, client = platform
    client.put("/api/settings/study", json=DEFAULT_RULES | {"answer_mode": "chaoxing_ai"})
    question = {"id": "10", "title": "Question", "type": "单选题", "code": "0", "options": ["First", "Second"], "supported": True}
    class Quiz(RecordingAdapter):
        writes = 0
        def list_jobs(self, course, chapter):
            return [Job("quiz", "300", "workid", "Quiz", False, 0, {}, {})]
        def chapter_paper(self, *args):
            return {"id": "paper-1", "questions": [question]}
        def chaoxing_answer(self, *args):
            return '["First"]'
        def save_answers(self, paper_id, answers, submit, complete):
            assert paper_id == "paper-1" and answers == {"10": ["First"]} and not submit
            self.__class__.writes += 1
            return {"saved": True, "submitted": False, "complete": True}
    worker, task = study_setup(platform, Quiz)
    worker.run_task(task)
    record = worker.db.one("SELECT * FROM tasks")
    assert record["state"] == "waiting_manual" and record["server_state"] != "confirmed"
    assert Quiz.writes == 1
    worker.service.action(task["id"], "retry")
    worker.run_task(worker.claim())
    assert Quiz.writes == 1


def test_uncertain_assessment_write_survives_restart_without_resubmission(platform):
    from backend.app.adapters.contracts import AdapterError
    _, _, client = platform
    client.put("/api/settings/study", json=DEFAULT_RULES | {"answer_mode": "chaoxing_ai", "work": True})
    class Interrupted(RecordingAdapter):
        opens = assessment_writes = 0
        def list_assessments(self, *args):
            return [{"id": "501", "kind": "work", "title": "Work", "status": "待做", "remaining": ""}]
        def assessment_questions(self, *args):
            self.__class__.opens += 1
            return {"id": "work:501", "questions": [{"id": "10", "title": "Question", "type": "判断题", "code": "3", "options": [], "supported": True}]}
        def chaoxing_answer(self, *args):
            return '["正确"]'
        def save_answers(self, *args):
            self.__class__.assessment_writes += 1
            raise AdapterError("network_error", "fixture network loss", True)
    worker, task = study_setup(platform, Interrupted)
    worker.run_task(task)
    assert "work:501" in json.loads(worker.db.one("SELECT checkpoint FROM tasks")["checkpoint"])["pending"]
    worker.db.execute("UPDATE tasks SET next_run_at=0")
    worker.run_task(worker.claim())
    assert Interrupted.opens == Interrupted.assessment_writes == 1
    assert worker.db.one("SELECT server_state FROM tasks")["server_state"] != "confirmed"


def test_basic_generator_settings_write_redacted_log_file(platform):
    config, app, client = platform
    body = {"concurrency": 2, "retry_seconds": 30, "max_attempts": 3, "log_retention_days": 30,
            "log_level": "debug", "completion_tone": True, "color_log": False, "log_out_file": True}
    assert client.put("/api/settings", json=body).status_code == 200
    app.state.db.log("password=fixture-log-secret", level="debug")
    content = (config.data_dir / "console.log").read_text(encoding="utf-8")
    assert "fixture-log-secret" not in content and "[debug]" in content
    data = yaml.safe_load(client.get("/api/configuration/export").text)
    assert data["setting"]["basicSetting"] == {"completionTone": 1, "colorLog": 0, "logOutFileSw": 1, "logLevel": "DEBUG"}


def test_metaso_uses_yatori_request_contract_with_verified_tls(monkeypatch):
    import httpx
    from backend.app.ai import preview_answer
    monkeypatch.setattr("backend.app.ai.validate_endpoint", lambda _: None)
    real = httpx.Client
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/chat/completions"
        assert body["format"] == "simple" and body["scope"] == "ducument" and "Question" in body["q"]
        return httpx.Response(200, json={"answer": '["First"]'})
    monkeypatch.setattr("backend.app.ai.httpx.Client", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    assert preview_answer({"enabled": True, "base_url": "https://metaso.cn/api/v1", "model": "fast", "api_key": "fixture", "api_style": "metaso"},
                          "Question", ["First", "Second"], structured=True) == '["First"]'


def test_http_question_bank_is_limited_to_explicit_lan_mode(platform):
    _, _, client = platform
    body = {"enabled": True, "url": "http://127.0.0.1:8083"}
    assert client.put("/api/settings/question-bank", json=body).status_code == 422
    assert client.put("/api/settings/question-bank", json=body | {"allow_lan": True}).status_code == 200
    assert client.put("/api/settings/question-bank", json=body | {"allow_lan": True, "url": "http://8.8.8.8"}).status_code == 422
