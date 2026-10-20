import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet, InvalidToken
from fastapi.testclient import TestClient

from backend.app.adapters.contracts import AdapterError, Job
from backend.app.config import Config
from backend.app.main import create_app
from backend.app.security import redact
from backend.app.services import PlatformService
from backend.app.worker import Worker


@pytest.fixture
def platform(tmp_path):
    config = Config(tmp_path / "data", Fernet.generate_key().decode(), "test-setup-" + "s" * 32, False, tmp_path / "web")
    app = create_app(config)
    with TestClient(app) as client:
        response = client.post("/api/auth/setup", json={"username": "admin", "password": "long-admin-secret", "setup_token": config.setup_token})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        yield config, app, client


def add_account(client, label="学习账号"):
    result = client.post("/api/accounts", json={"label": label, "username": "13800138000", "password": "account-canary-secret"})
    assert result.status_code == 200
    return result.json()["id"]


def add_course(app, account_id):
    service = PlatformService(app.state.db, app.state.vault)
    service.save_courses(account_id, [{"courseId": "100", "clazzId": "200", "cpi": "private-course-token",
                                       "title": "课程一", "teacher": "教师"}])
    return app.state.db.one("SELECT id FROM courses WHERE account_id=?", (account_id,))["id"]


def test_authentication_csrf_and_logout(platform):
    config, app, client = platform
    other = TestClient(app)
    assert other.get("/api/accounts").status_code == 401
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/accounts", json={"label": "a", "username": "u", "password": "p"}).status_code == 403
    client.headers["X-CSRF-Token"] = client.get("/api/auth/status").json()["csrf"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "long-admin-secret"}).status_code == 200


def test_secure_cookie_and_foreign_origin(platform):
    config, app, client = platform
    token = client.cookies.get("study_session")
    stored = app.state.db.one("SELECT * FROM sessions")
    assert token != stored["token_hash"]
    assert client.post("/api/auth/logout", headers={"Origin": "https://external.invalid"}).status_code == 403
    response = client.get("/api/accounts")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


def test_ciphertext_persistence_and_api_surfaces(platform):
    config, app, client = platform
    account_id = add_account(client)
    course_id = add_course(app, account_id)
    record = app.state.db.one("SELECT * FROM accounts")
    assert "account-canary-secret" not in record["credentials"]
    assert app.state.vault.open(record["credentials"])["password"] == "account-canary-secret"
    response = client.get("/api/courses").text + client.get("/api/accounts").text
    assert "private-course-token" not in response
    assert "account-canary-secret" not in response
    assert "13800138000" not in response
    fresh_app = create_app(config)
    assert fresh_app.state.db.one("SELECT id FROM courses")["id"] == course_id
    bad = Config(config.data_dir, Fernet.generate_key().decode(), config.setup_token, False)
    with pytest.raises(InvalidToken):
        create_app(bad)


def test_validation_does_not_echo_secrets_and_setup_is_once(platform):
    config, app, client = platform
    response = client.post("/api/accounts", json={"label": "", "username": "u", "password": "private-invalid-value"})
    assert response.status_code == 422
    assert "private-invalid-value" not in response.text
    assert client.post("/api/auth/setup", json={"username": "admin2", "password": "long-admin-secret", "setup_token": config.setup_token}).status_code == 409


def test_login_rate_limit(platform):
    config, app, client = platform
    results = [client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code for _ in range(10)]
    assert results[-1] == 429  # Setup counts against the same client window.


def test_duplicate_queue_and_controls(platform):
    config, app, client = platform
    account_id = add_account(client)
    task = client.post(f"/api/accounts/{account_id}/sync").json()
    assert "checkpoint" not in task
    assert client.post(f"/api/accounts/{account_id}/sync").status_code == 409
    assert client.delete(f"/api/accounts/{account_id}").status_code == 409
    action = f"/api/tasks/{task['id']}/action"
    assert client.post(action, json={"action": "pause"}).json()["state"] == "paused"
    assert client.post(action, json={"action": "resume"}).json()["state"] == "queued"
    assert client.post(action, json={"action": "retry"}).status_code == 409
    assert client.post(action, json={"action": "stop"}).json()["state"] == "stopped"
    assert client.delete(f"/api/accounts/{account_id}").status_code == 200


def test_claim_serializes_account_and_is_atomic(platform):
    config, app, client = platform
    service = PlatformService(app.state.db, app.state.vault)
    a, b = add_account(client, "甲"), add_account(client, "乙")
    service.queue(a, "login")
    service.queue(a, "sync_courses")
    service.queue(b, "login")
    worker = Worker(config)
    with ThreadPoolExecutor(3) as pool:
        claimed = [x for x in pool.map(lambda _: worker.claim(), range(3)) if x]
    assert len(claimed) == 2
    assert {t["account_id"] for t in claimed} == {a, b}
    assert len({t["id"] for t in claimed}) == 2


class RecordingAdapter:
    writes = 0
    confirms = False
    chapter_confirmed = False
    fail_after_write = False
    passed_at_start = False

    def __init__(self, credentials, cookies, control):
        self.control = control

    def login(self, *args):
        self.control()

    def list_courses(self):
        return []

    def list_chapters(self, course):
        return [{"id": "300", "title": "章节", "jobCount": 1,
                 "has_finished": self.chapter_confirmed and type(self).writes > 0, "need_unlock": False}]

    def list_jobs(self, course, chapter):
        return [Job("job-1", "300", "document", "文档", self.passed_at_start or (self.confirms and type(self).writes > 0), 0, {}, {})]

    def execute(self, course, job, control, progress):
        control()
        type(self).writes += 1
        progress(1)
        if self.fail_after_write:
            raise AdapterError("network_error", "网络暂时不可用", True)

    def export_cookies(self):
        return [{"name": "_uid", "value": "cookie-canary", "domain": ".chaoxing.com", "path": "/"}]

    def close(self):
        pass


def study_setup(platform, adapter_type):
    config, app, client = platform
    account_id = add_account(client)
    course_id = add_course(app, account_id)
    client.post(f"/api/courses/{course_id}/study")
    worker = Worker(config, adapter_type)
    return worker, worker.claim()


def test_success_requires_server_confirmation(platform):
    class Confirmed(RecordingAdapter):
        writes = 0
        confirms = True
        chapter_confirmed = True
    worker, task = study_setup(platform, Confirmed)
    worker.run_task(task)
    row = worker.db.one("SELECT * FROM tasks WHERE id=?", (task["id"],))
    assert row["state"] == "succeeded" and row["server_state"] == "confirmed"
    assert row["progress"] == 100
    assert Confirmed.writes == 1
    assert "cookie-canary" not in worker.db.one("SELECT cookies FROM accounts")["cookies"]


def test_request_success_stays_unconfirmed_and_retry_does_not_resend(platform):
    class Unconfirmed(RecordingAdapter):
        writes = 0
    worker, task = study_setup(platform, Unconfirmed)
    worker.run_task(task)
    assert worker.db.one("SELECT state FROM tasks")["state"] == "awaiting_confirmation"
    assert Unconfirmed.writes == 1
    worker.service.action(task["id"], "retry")
    worker.run_task(worker.claim())
    assert Unconfirmed.writes == 1
    assert worker.db.one("SELECT server_state FROM tasks")["server_state"] == "pending"


def test_crash_after_write_recovers_without_duplicate_execution(platform):
    class Interrupted(RecordingAdapter):
        writes = 0
        fail_after_write = True
    worker, task = study_setup(platform, Interrupted)
    worker.run_task(task)
    assert worker.db.one("SELECT state FROM tasks")["state"] == "recovering"
    worker.update(task["id"], next_run_at=0)
    worker.recover()
    worker.run_task(worker.claim())
    assert Interrupted.writes == 1
    assert worker.db.one("SELECT state FROM tasks")["state"] == "awaiting_confirmation"


def test_confirmed_job_checkpoint_is_cleared_without_execution(platform):
    class Passed(RecordingAdapter):
        writes = 0
        passed_at_start = True
    worker, task = study_setup(platform, Passed)
    checkpoint = {"pending": {"300:job-1": {"kind": "document"}}}
    worker.checkpoint(task["id"], checkpoint)
    task["checkpoint"] = json.dumps(checkpoint)
    worker.run_task(task)
    assert Passed.writes == 0
    assert not json.loads(worker.db.one("SELECT checkpoint FROM tasks")["checkpoint"])["pending"]


def test_restart_honors_pause_stop_and_closes_history(platform):
    config, app, client = platform
    service = PlatformService(app.state.db, app.state.vault)
    a = add_account(client)
    service.queue(a, "login")
    worker = Worker(config)
    task = worker.claim()
    service.action(task["id"], "pause")
    worker.recover()
    assert worker.db.one("SELECT state FROM tasks")["state"] == "paused"
    assert worker.db.one("SELECT state,finished_at FROM runs")["state"] == "interrupted"
    service.action(task["id"], "resume")
    task = worker.claim()
    service.action(task["id"], "stop")
    worker.recover()
    assert worker.db.one("SELECT state FROM tasks")["state"] == "stopped"


def test_paused_task_does_not_construct_adapter(platform):
    class MustNotRun:
        def __init__(self, *args):
            pytest.fail("paused task constructed an adapter")
    worker, task = study_setup(platform, MustNotRun)
    worker.service.action(task["id"], "pause")
    worker.run_task(task)
    assert worker.db.one("SELECT state FROM tasks")["state"] == "paused"


def test_log_redaction_and_cursor(platform):
    config, app, client = platform
    app.state.db.log("password=my-secret Cookie: _uid=private-cookie")
    app.state.db.log("任务完成")
    logs = client.get("/api/logs").json()
    assert "my-secret" not in str(logs)
    assert "private-cookie" not in str(logs)
    assert client.get(f"/api/logs?after={logs[-2]['id']}").json()[-1]["message"] == "任务完成"
    assert redact("Bearer secret", ["secret"]) == "Bearer [已过滤]"


def test_settings_are_live_and_ai_key_stays_encrypted(platform):
    config, app, client = platform
    update = {"concurrency": 4, "retry_seconds": 5, "max_attempts": 2, "log_retention_days": 7}
    assert client.put("/api/settings", json=update).json()["concurrency"] == 4
    assert Worker(config).db.settings()["concurrency"] == 4
    client.put("/api/settings/ai", json={"enabled": False, "base_url": "https://api.openai.com/v1", "model": "model", "api_key": "ai-key-canary"})
    settings = client.get("/api/settings").json()
    assert settings["ai"]["key_configured"] is True
    assert "ai-key-canary" not in str(settings)
    assert "ai-key-canary" not in app.state.db.one("SELECT value FROM settings WHERE key='ai'")["value"]
    assert client.post("/api/ai/preview", json={"question": "问题", "options": []}).status_code == 409
