"""Contracts for original Console execution, private config and process ownership."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
import yaml
from fastapi import HTTPException

from backend.app.console_process import ConsoleError, ConsoleProcess, console_config
from backend.app.db import Database
from backend.app.services import PlatformService
from backend.app.worker import Worker, TaskInterrupted
from backend.tests.test_platform import platform, add_account, add_course


@pytest.fixture
def fake_console(tmp_path):
    script = tmp_path / "console.py"
    script.write_text('''import json, os, sys, time
from pathlib import Path
import yaml
config = yaml.safe_load(Path('config.yaml').read_text(encoding='utf-8'))
Path('observed.json').write_text(json.dumps({'config':config,'argv':sys.argv,'cache':os.environ['XDG_CACHE_HOME']}))
print('original stdout fixture-secret', flush=True)
print('original stderr', file=sys.stderr, flush=True)
if config.get('query_error'):
    Path('query-result.json').write_text(json.dumps({'ok':False,'error':config['query_error']}))
    sys.exit(config.get('result_exit', 2))
if config.get('hang'):
    Path('pid').write_text(str(os.getpid()))
    time.sleep(120)
if config.get('exit'):
    sys.exit(config['exit'])
if 'YATORI_BRIDGE_MODE' in os.environ and not config.get('missing'):
    Path('query-result.json').write_text(json.dumps({'ok':True,'data':[]}))
''', encoding="utf-8")
    return [sys.executable, str(script)]


def test_subprocess_captures_original_streams_and_cleans_credentials(platform, fake_console):
    config, _, _ = platform
    lines = []
    result = ConsoleProcess(config, fake_console).run(1, {"password": "fixture-secret"}, "", ["fixture-secret"], lambda: None,
        lambda line, level: lines.append(line), "courses")
    assert result == []
    assert lines == ["original stdout [已过滤]", "original stderr"]
    folder = config.data_dir / "console/1"
    observed = json.loads((folder / "observed.json").read_text())
    assert "fixture-secret" not in str(observed["argv"])
    assert Path(observed["cache"]).parent == folder
    assert not any((folder / name).exists() for name in ("config.yaml", "query.json", "query-result.json", "ip.txt"))


@pytest.mark.parametrize("value", [{"exit": 2}, {"missing": True}])
def test_bad_exit_or_missing_query_result_fails(platform, fake_console, value):
    config, _, _ = platform
    with pytest.raises(ConsoleError):
        ConsoleProcess(config, fake_console).run(1, value, "", [], lambda: None, lambda *_: None, "courses")
    assert not (config.data_dir / "console/1/config.yaml").exists()


def test_stop_reaps_real_child_and_removes_private_config(platform, fake_console):
    config, _, _ = platform
    started = time.monotonic()
    children = []
    def control():
        if (config.data_dir / "console/1/pid").exists():
            raise TaskInterrupted("stopped")
        assert time.monotonic() - started < 10
    import backend.app.console_process as module
    original = module.subprocess.Popen
    def record(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    from unittest.mock import patch
    with patch.object(module.subprocess, "Popen", record), pytest.raises(TaskInterrupted):
        ConsoleProcess(config, fake_console).run(1, {"hang": True}, "", [], control, lambda *_: None)
    assert children[0].poll() is not None
    assert not (config.data_dir / "console/1/config.yaml").exists()


@pytest.mark.parametrize("exit_code", [0, 2])
def test_query_error_surfaces_redacted_platform_message(platform, fake_console, exit_code):
    config, _, _ = platform
    with pytest.raises(ConsoleError) as caught:
        ConsoleProcess(config, fake_console).run(1,
            {"query_error": "平台提示：登录失效 fixture-secret token=private-token", "result_exit": exit_code},
            "", ["fixture-secret"], lambda: None, lambda *_: None, "chapters")
    message = str(caught.value)
    assert "平台提示：登录失效" in message
    assert "fixture-secret" not in message and "private-token" not in message
    assert not (config.data_dir / "console/1/query-result.json").exists()


def test_failed_progress_query_keeps_snapshot_and_exposes_reason(platform, fake_console):
    config, app, client = platform
    account = add_account(client)
    course = add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    service.save_courses(account, [{"courseId": "100", "clazzId": "200", "title": "课程一", "original": {"courseId": "100"}}])
    service.save_chapters(course, [{"id": "1", "title": "已完成章节", "has_finished": True}])
    before = service.learning.snapshot(account)["courses"][0]
    class Process:
        def __init__(self, cfg): self.native = ConsoleProcess(cfg, fake_console)
        def run(self, account_id, value, proxy, secrets, control, log, mode, original):
            return self.native.run(account_id, value | {"query_error": "平台未返回章节进度；平台提示：请求参数不正确 account-canary-secret"}, proxy, secrets, control, log, mode, original)
    assert client.post(f"/api/courses/{course}/sync").status_code == 200
    worker = Worker(config, Process)
    worker.run_task(worker.claim())
    result = client.get(f"/api/accounts/{account}/learning").json()["courses"][0]
    assert result["progress"] == before["progress"] == 100
    assert result["progress_synced_at"] == before["progress_synced_at"]
    assert result["progress_refresh_state"] == "failed"
    assert "平台提示：请求参数不正确" in result["progress_refresh_message"]
    assert "account-canary-secret" not in str(result)


@pytest.mark.skipif(os.name == "nt", reason="POSIX inherited process ownership")
def test_orphan_child_owns_account_directory_until_exit(platform, fake_console):
    import signal
    config, _, _ = platform
    script = """import json, sys
from pathlib import Path
from types import SimpleNamespace
from backend.app.console_process import ConsoleProcess
config = SimpleNamespace(data_dir=Path(sys.argv[1]), onnx_library='', model_dir='')
ConsoleProcess(config, json.loads(sys.argv[2])).run(1, {'hang': True, 'password': 'fixture-secret'}, '', [], lambda: None, lambda *_: None)
"""
    parent = subprocess.Popen([sys.executable, "-c", script, str(config.data_dir), json.dumps(fake_console)],
                              cwd=Path(__file__).resolve().parents[2], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    folder = config.data_dir / "console/1"
    native_pid = None
    contender = None
    results = []
    errors = []
    waiting = threading.Event()
    checks = 0

    def control():
        nonlocal checks
        checks += 1
        if checks >= 3:
            waiting.set()

    def replace():
        try:
            results.append(ConsoleProcess(config, fake_console).run(1, {}, "", [], control, lambda *_: None, "courses"))
        except BaseException as error:
            errors.append(error)

    try:
        deadline = time.monotonic() + 10
        while not (folder / "pid").is_file() and time.monotonic() < deadline:
            assert parent.poll() is None, "Fixture parent exited before spawning its Console child"
            time.sleep(0.02)
        assert (folder / "pid").is_file()
        native_pid = int((folder / "pid").read_text())
        parent.kill()
        parent.wait(timeout=5)
        original_config = (folder / "config.yaml").read_bytes()
        (folder / "query-result.json").write_text("owned by running child")
        contender = threading.Thread(target=replace, daemon=True)
        contender.start()
        assert waiting.wait(5), "Replacement did not wait for the account directory owner"
        assert contender.is_alive()
        assert (folder / "config.yaml").read_bytes() == original_config
        assert (folder / "query-result.json").read_text() == "owned by running child"
        os.kill(native_pid, signal.SIGTERM)
        native_pid = None
        contender.join(timeout=10)
        assert not contender.is_alive()
        assert errors == []
        assert results == [[]]
        assert not (folder / "config.yaml").exists()
        assert not (folder / "query-result.json").exists()
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=5)
        if native_pid is not None:
            try:
                os.kill(native_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if contender is not None:
            contender.join(timeout=5)


@pytest.mark.skipif(os.name == "nt", reason="POSIX inherited process ownership")
def test_waiting_for_account_directory_remains_cancellable(platform, fake_console):
    config, _, _ = platform
    folder = config.data_dir / "console/1"
    folder.mkdir(parents=True)
    (folder / "config.yaml").write_text("current owner")
    def cancel():
        raise TaskInterrupted("paused")
    with ConsoleProcess.ownership(folder, lambda: None):
        with pytest.raises(TaskInterrupted):
            ConsoleProcess(config, fake_console).run(1, {}, "", [], cancel, lambda *_: None)
        assert (folder / "config.yaml").read_text() == "current owner"


def test_account_batch_uses_original_yaml_and_process_exit_is_not_course_completion(platform):
    config, app, client = platform
    account = add_account(client)
    first = add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    service.save_courses(account, [{"courseId": "101", "clazzId": "201", "title": "课程二"}])
    rules = service.study_settings(account) | {"video_mode": "multi_course", "include_courses": ["100", "101"]}
    app.state.db.execute("INSERT INTO learning_rules VALUES(?,?)", (account, json.dumps(rules)))
    queued = service.queue_courses(account)
    assert len(queued["tasks"]) == 1
    assert queued["tasks"][0]["course_id"] is None
    seen = []
    class Process:
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            seen.append(value)
            assert mode is None and course is None and account_id == account
            log("original console output", "info")
    worker = Worker(config, Process)
    worker.run_task(worker.claim())
    custom = seen[0]["users"][0]["coursesCustom"]
    assert custom["includeCourses"] == ["课程一", "课程二"]
    assert custom["videoModel"] == 2 and custom["cxWorkSw"] == 0
    assert seen[0]["setting"]["basicSetting"]["webModel"] == 0
    assert "console" not in seen[0]
    result = app.state.db.one("SELECT state,server_state,progress FROM tasks")
    assert result == {"state": "completed", "server_state": "unknown", "progress": 0}
    logs = client.get(f"/api/logs?account_id={account}&source=yatori").json()
    assert [line["message"] for line in logs] == ["original console output"]


def test_same_account_is_serial_even_in_multi_course_mode(platform):
    config, app, client = platform
    account = add_account(client)
    course = add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    service.queue(account, "study", course, {"video_mode": "multi_course"})
    service.queue(account, "sync_courses")
    worker = Worker(config)
    assert worker.claim()
    assert worker.claim() is None
    other = add_account(client, "另一账号")
    service.queue(other, "login")
    assert worker.claim()["account_id"] == other


def test_upgrade_preserves_history_and_requires_fresh_start(platform):
    config, app, client = platform
    account = add_account(client)
    service = PlatformService(app.state.db, app.state.vault)
    task = service.queue(account, "login")
    app.state.db.execute("UPDATE tasks SET checkpoint='{}',state='running' WHERE id=?", (task["id"],))
    app.state.db.execute("DELETE FROM schema_migrations WHERE version=3")
    db = Database(app.state.db.path)
    assert db.one("SELECT state FROM tasks")["state"] == "stopped"
    assert len(db.rows("SELECT * FROM accounts")) == 1
    with pytest.raises(HTTPException):
        service.action(task["id"], "retry")
    assert service.queue(account, "login")["state"] == "queued"


def test_restart_pauses_execution_and_resume_keeps_console_rules(platform):
    config, app, client = platform
    account = add_account(client)
    service = PlatformService(app.state.db, app.state.vault)
    task = service.queue(account, "login")
    worker = Worker(config)
    assert worker.claim()
    worker.recover()
    assert app.state.db.one("SELECT state FROM tasks")["state"] == "paused"
    assert service.action(task["id"], "resume")["state"] == "queued"


def test_duplicate_course_names_cannot_silently_expand_selection(platform):
    config, app, client = platform
    account = add_account(client)
    course = add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    service.save_courses(account, [{"courseId": "102", "clazzId": "202", "title": "课程一"}])
    with pytest.raises(HTTPException):
        service.queue(account, "study", course)


def test_reviewed_batch_does_not_expand_after_course_sync(platform):
    _, app, client = platform
    account = add_account(client)
    add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    plan = service.study_plan(account)
    service.save_courses(account, [{"courseId": "103", "clazzId": "203", "title": "后来同步的课程"}])
    task = service.queue_courses(account, plan)["tasks"][0]
    assert json.loads(task["checkpoint"])["course_titles"] == ["课程一"]


def test_management_threshold_keeps_all_original_console_output(platform, fake_console):
    config, app, client = platform
    account = add_account(client)
    service = PlatformService(app.state.db, app.state.vault)
    task = service.queue(account, "login")
    app.state.db.set_setting("log_level", "error")
    value, proxy, secrets = console_config(service, service.account(account), service.study_settings(account))
    assert value["setting"]["basicSetting"]["logLevel"] == "INFO"
    ConsoleProcess(config, fake_console).run(account, value, proxy, secrets, lambda: None,
        lambda text, level: app.state.db.log(text, task["id"], level, source="yatori"), "courses")
    assert len(client.get(f"/api/logs?account_id={account}&source=yatori").json()) == 2


def test_native_debug_mode_labels_original_unprefixed_output(platform, fake_console):
    config, _, _ = platform
    levels = []
    ConsoleProcess(config, fake_console).run(1, {"setting": {"basicSetting": {"logLevel": "DEBUG"}}}, "", [], lambda: None,
        lambda text, level: levels.append(level), "courses")
    assert levels == ["debug", "debug"]
