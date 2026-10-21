"""Contracts for original Console execution, private config and process ownership."""
import json
import os
from pathlib import Path
import subprocess
import sys
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
