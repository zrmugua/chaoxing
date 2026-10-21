import io
import json
import sqlite3
import pytest

from backend.app.adapters.yatori import YatoriAdapter
from backend.app.adapters.contracts import AdapterError, Job
from backend.app.db import Database
from backend.app.services import PlatformService
from backend.app.worker import Worker
from backend.app.security import redact
from backend.tests.test_platform import platform, add_account


class ConsoleProcess:
    def __init__(self, *args, **kwargs):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("\n".join(json.dumps(value) for value in [
            {"event": "log", "message": "\x1b[32m原始输出 fixture-password Cookie: sid=fixture-cookie\x1b[0m"},
            {"id": 1, "ok": True, "data": {"engine": "yatori", "upstream": "fixture"}},
            {"event": "log", "message": "[ERROR] network response unavailable"},
            {"id": 2, "ok": True, "data": []},
        ]) + "\n")
        self.dead = False

    def poll(self):
        return 0 if self.dead else None

    def kill(self):
        self.dead = True

    def wait(self, timeout=None):
        return 0


def test_console_events_are_redacted_without_changing_rpc_results():
    lines = []
    with YatoriAdapter({"password": "fixture-password"}, process_factory=ConsoleProcess,
                       log_callback=lambda text, level: lines.append((text, level))) as adapter:
        assert adapter.export_cookies() == []
    assert len(lines) == 2 and "原始输出" in lines[0][0] and lines[1][1] == "error"
    assert all(secret not in str(lines) for secret in ("fixture-password", "fixture-cookie", "\x1b"))


def test_account_and_source_log_filters_keep_cursor_scope(platform):
    config, app, client = platform
    first, second = add_account(client, "甲账号"), add_account(client, "乙账号")
    service = PlatformService(app.state.db, app.state.vault)
    tasks = [service.queue(account, "login") for account in (first, second)]
    app.state.db.log("甲的原始日志", tasks[0]["id"], source="yatori")
    app.state.db.log("乙的原始日志", tasks[1]["id"], source="yatori")
    query = f"/api/logs?account_id={first}&source=yatori"
    logs = client.get(query).json()
    assert len(logs) == 1 and logs[0]["account_label"] == "甲账号"
    assert logs[0]["message"] == "甲的原始日志"
    app.state.db.log("乙的新日志", tasks[1]["id"], source="yatori")
    assert client.get(query + f"&after={logs[0]['id']}").json() == []
    app.state.db.log("甲的新日志", tasks[0]["id"], source="yatori")
    assert [line["message"] for line in client.get(query + f"&after={logs[0]['id']}").json()] == ["甲的新日志"]
    assert client.get(query + f"&task_id={tasks[1]['id']}").json() == []
    assert client.get("/api/logs?source=unknown").status_code == 422
    assert all(line["source"] == "console" for line in client.get("/api/logs?source=console").json())


def test_worker_binds_native_logs_to_the_task_account(platform, monkeypatch):
    from functools import partial
    config, app, client = platform
    account = add_account(client)
    task = PlatformService(app.state.db, app.state.vault).queue(account, "login")
    worker = Worker(config, partial(YatoriAdapter, process_factory=ConsoleProcess))
    with worker.create_adapter(task, {"password": "fixture-password"}, [], lambda: None) as adapter:
        adapter.export_cookies()
    logs = client.get(f"/api/logs?account_id={account}&source=yatori").json()
    assert len(logs) == 2 and all(line["task_id"] == task["id"] for line in logs)
    assert "fixture-password" not in str(logs)


def test_existing_database_keeps_logs_when_adding_source(tmp_path):
    path = tmp_path / "previous.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE logs(id INTEGER PRIMARY KEY,task_id INTEGER,level TEXT,message TEXT,created_at REAL)")
        connection.execute("INSERT INTO logs VALUES(1,NULL,'info','历史日志',0)")
    db = Database(path)
    assert db.one("SELECT message,source FROM logs") == {"message": "历史日志", "source": "console"}
    Database(path)
    assert db.one("SELECT count(*) AS count FROM logs")["count"] == 1


def test_worker_transmits_core_logging_configuration_and_event_level(platform):
    from functools import partial
    config, app, client = platform
    account = add_account(client, "日志账号")
    worker = Worker(config, partial(YatoriAdapter, process_factory=ConsoleProcess))
    worker.db.set_setting("log_level", "debug")
    task = worker.service.queue(account, "login")
    with worker.create_adapter(task, {}, [], lambda: None) as adapter:
        initial = json.loads(adapter._process.stdin.getvalue().splitlines()[0])
        assert initial["args"]["credentials"]["log_level"] == "debug"
        assert initial["args"]["credentials"]["log_label"] == "日志账号"
        adapter._console_log("Core diagnostic output", "debug")
    log = worker.db.one("SELECT level,source,task_id FROM logs WHERE message='Core diagnostic output'")
    assert log == {"level": "debug", "source": "yatori", "task_id": task["id"]}


def test_cookie_flags_preserve_console_timestamps_and_numbers():
    lines = []
    with YatoriAdapter({}, [{"name": "thirdRegist", "value": "0"}, {"name": "session", "value": "fixture-session-cookie"}],
                       process_factory=ConsoleProcess, log_callback=lambda text, _: lines.append(text)) as adapter:
        adapter._remember_log_cookies([{"name": "thirdRegist", "value": "1"}])
        adapter._console_log("2026/10/20 progress=100 duration=300 fixture-session-cookie")
    assert lines[-1] == "2026/10/20 progress=100 duration=300 [已过滤]"


def test_console_request_urls_filter_task_signatures():
    text = 'Get "https://mooc1.chaoxing.com/mooc-ans/multimedia/log/a/42/private-dtoken?playingTime=10&otherInfo=nodeId_300-enc_private-server-token&enc=private-signature&videoFaceCaptureEnc=private-face&attDurationEnc=private-duration": network unavailable'
    result = redact(text)
    assert all(value not in result for value in ("private-dtoken", "private-server-token", "private-signature", "private-face", "private-duration"))
    assert "playingTime=10" in result and "nodeId_300-enc_" in result and "network unavailable" in result


@pytest.mark.parametrize("reason,expected", [
    ("captcha", "输入验证码"), ("face", "人脸识别"),
    ("rate_limit", "访问过于频繁"), ("paper_notice", "考试须知"),
    ("unknown", "要求人工处理"),
])
def test_manual_reason_reaches_task_error_text(reason, expected):
    class Restricted(ConsoleProcess):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.stdout = io.StringIO("\n".join(json.dumps(value) for value in [
                {"id": 1, "ok": True, "data": {"engine": "yatori"}},
                {"id": 2, "ok": False, "code": "manual_required", "reason": reason, "card_index": 1},
            ]) + "\n")
    with YatoriAdapter({}, process_factory=Restricted) as adapter:
        with pytest.raises(AdapterError) as error:
            adapter.chapter_paper({}, Job("51", "300", "workid", "测验", False, 1, {}, {}))
    assert error.value.code == "manual_required"
    assert expected in str(error.value) and "第 2 张任务卡" in str(error.value)
