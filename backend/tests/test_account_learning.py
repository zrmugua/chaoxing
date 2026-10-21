"""Account intent, revision and original-process lifecycle integration contracts."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from backend.app.console_process import ConsoleError
from backend.app.db import Database
from backend.app.services import PlatformService
from backend.app.worker import Worker
from backend.tests.test_platform import platform, add_account, add_course


def fixture_account(platform):
    config, app, client = platform
    account = add_account(client)
    first = add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    service.save_courses(account, [{"courseId": "101", "clazzId": "201", "title": "课程二", "original": {"CourseID": "101"}}])
    second = app.state.db.one("SELECT id FROM courses WHERE remote_id='101'")["id"]
    return config, app, client, account, first, second, service


def start_selection(service, account, course_ids):
    row = service.learning.snapshot(account)
    row = service.learning.save(account, course_ids, row["revision"])
    return service.learning.action(account, "start", row["revision"])


def test_selection_api_revisions_pause_stop_and_empty(platform):
    _, app, client, account, first, second, service = fixture_account(platform)
    url = f"/api/accounts/{account}/learning"
    initial = client.get(url).json()
    assert (initial["state"], initial["revision"], initial["selected_course_ids"]) == ("idle", 0, [])
    assert initial["courses"][0]["progress"] is None
    selected = client.put(url, json={"course_ids": [first], "revision": 0}).json()
    assert selected["revision"] == 1 and selected["selected_course_ids"] == [first]
    assert client.put(url, json={"course_ids": [second], "revision": 0}).status_code == 409
    assert client.post(url + "/action", json={"action": "start", "revision": 0}).status_code == 409
    paused = client.post(url + "/action", json={"action": "pause", "revision": 1}).json()
    selected = client.put(url, json={"course_ids": [second], "revision": paused["revision"]}).json()
    assert selected["state"] == selected["desired_state"] == "paused"
    assert app.state.db.rows("SELECT * FROM tasks") == []
    stopped = client.post(url + "/action", json={"action": "stop"}).json()
    assert stopped["selected_course_ids"] == [second]
    assert stopped["state"] == "stopped"
    started = client.post(url + "/action", json={"action": "start"}).json()
    assert started["state"] == "queued"
    empty = client.put(url, json={"course_ids": [], "revision": started["revision"]}).json()
    assert empty["selected_course_ids"] == [] and empty["desired_state"] == "stopped"
    assert Worker(platform[0]).claim() is None
    assert client.post(url + "/action", json={"action": "resume"}).status_code == 409


def test_concurrent_selection_compare_and_swap_has_one_winner(platform):
    _, _, _, account, first, second, service = fixture_account(platform)
    revision = service.learning.snapshot(account)["revision"]
    barrier = threading.Barrier(2)
    def save(course):
        barrier.wait()
        try:
            return service.learning.save(account, [course], revision)["selected_course_ids"]
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, [first, second]))
    assert results.count(409) == 1
    assert service.learning.snapshot(account)["revision"] == revision + 1


def test_rapid_live_edits_wait_for_reap_and_start_only_latest_selection(platform):
    config, app, _, account, first, second, service = fixture_account(platform)
    started, stopping, reaped = threading.Event(), threading.Event(), threading.Event()
    snapshots = []
    class Process:
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            snapshots.append(value["users"][0]["coursesCustom"]["includeCourses"])
            log("[学习通][账号] [课程一] 正在学习该课程", "info")
            started.set()
            try:
                while True:
                    control()
                    time.sleep(.01)
            finally:
                stopping.set()
                assert reaped.wait(5)
    start_selection(service, account, [first])
    worker = Worker(config, Process)
    task = worker.claim()
    thread = threading.Thread(target=worker.run_task, args=(task,))
    thread.start()
    try:
        assert started.wait(5)
        row = service.learning.snapshot(account)
        assert row["active_course_titles"] == ["课程一"]
        assert row["latest_activity"]["course_title"] == "课程一"
        row = service.learning.save(account, [second], row["revision"])
        assert row["state"] == "applying"
        assert stopping.wait(5)
        row = service.learning.save(account, [first, second], row["revision"])
        row = service.learning.save(account, [second], row["revision"])
        assert worker.claim() is None
        assert snapshots == [["课程一"]]
    finally:
        reaped.set()
        thread.join(5)
    assert not thread.is_alive()
    replacement = worker.claim()
    assert json.loads(replacement["checkpoint"])["course_titles"] == ["课程二"]
    assert app.state.db.one("SELECT COUNT(*) AS n FROM tasks WHERE state='running'")["n"] == 1
    assert service.learning.snapshot(account)["active_course_titles"] == []


@pytest.mark.parametrize("query_kind", ["sync_courses", "sync_chapters", "refresh_account"])
def test_queries_interrupt_learning_then_resume_latest_intent(platform, query_kind):
    config, app, _, account, first, second, service = fixture_account(platform)
    called = []
    class Process:
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            control()
            called.append(mode)
            if mode == "courses":
                return [{"courseId": "100", "clazzId": "200", "title": "课程一", "original": {"CourseID": "100"}},
                        {"courseId": "101", "clazzId": "201", "title": "课程二", "original": {"CourseID": "101"}}]
            return [{"id": "c1", "title": "章节一", "has_finished": True}, {"id": "c2", "title": "章节二", "has_finished": False}]
    start_selection(service, account, [first])
    worker = Worker(config, Process)
    old = worker.claim()
    if query_kind == "refresh_account":
        service.learning.action(account, "refresh")
    else:
        service.queue(account, query_kind, first if query_kind == "sync_chapters" else None)
    worker.tick()
    assert worker.claim() is None
    # Finishing models the boundary after the original process has been reaped.
    worker.finish(old, "stopped", "Console 进程已停止")
    query = worker.claim()
    assert query["kind"] == query_kind
    worker.run_task(query)
    row = service.learning.snapshot(account)
    assert row["desired_state"] == "running" and row["state"] == "queued"
    assert row["refresh_pending"] is False
    if query_kind != "sync_courses":
        assert row["courses"][0]["progress"] == 50
        assert row["courses"][0]["progress_synced_at"] is not None
    if query_kind == "sync_chapters":
        assert row["courses"][0]["progress_refresh_state"] == "succeeded"
        assert row["courses"][1]["progress"] is None
        assert row["courses"][1]["progress_refresh_state"] is None
    assert worker.claim()["kind"] == "study"
    assert called == (["courses", "chapters", "chapters"] if query_kind == "refresh_account" else ["courses" if query_kind == "sync_courses" else "chapters"])


@pytest.mark.parametrize("failure", ["courses", "chapters"])
def test_refresh_failure_preserves_progress_and_resumes_learning(platform, failure):
    config, _, _, account, first, _, service = fixture_account(platform)
    service.save_chapters(first, [{"id": "c1", "title": "已确认章节", "has_finished": True}])
    timestamp = service.learning.snapshot(account)["courses"][0]["progress_synced_at"]
    class Process:
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            if mode == failure:
                raise ConsoleError("课程查询失败，请重试")
            return [{"courseId": "100", "clazzId": "200", "title": "课程一", "original": {"CourseID": "100"}}]
    start_selection(service, account, [first])
    service.learning.action(account, "refresh")
    worker = Worker(config, Process)
    query = worker.claim()
    assert query["kind"] == "refresh_account"
    worker.run_task(query)
    row = service.learning.snapshot(account)
    assert row["refresh_error"] and not row["refresh_pending"]
    assert row["desired_state"] == "running" and row["state"] == "queued"
    assert row["courses"][0]["progress"] == 100
    assert row["courses"][0]["progress_synced_at"] == timestamp


def test_console_exit_preserves_confirmed_progress_and_activity_is_precise(platform):
    config, _, _, account, first, second, service = fixture_account(platform)
    service.save_chapters(first, [{"id": "1", "title": "一", "has_finished": True}, {"id": "2", "title": "二"}])
    start_selection(service, account, [first, second])
    seen = []
    class Process:
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            assert service.learning.snapshot(account)["active_course_titles"] == []
            log("[学习通][账号] [课程一] 正在学习该课程", "info")
            seen.append(service.learning.snapshot(account)["active_course_titles"])
            log("[学习通][账号] [课程一] 课程学习完毕", "info")
            seen.append(service.learning.snapshot(account)["active_course_titles"])
    worker = Worker(config, Process)
    worker.run_task(worker.claim())
    row = service.learning.snapshot(account)
    assert row["state"] == "completed" and row["desired_state"] == "stopped"
    assert seen == [["课程一"], []]
    assert [course["progress"] for course in row["courses"]] == [50, None]
    assert row["running_course_titles"] == [] and row["active_course_titles"] == []
    assert row["selected_course_ids"] == [first, second]
    assert worker.claim() is None


@pytest.mark.parametrize("claimed", [False, True])
def test_restart_pauses_intent_and_retains_selection(platform, claimed):
    config, _, _, account, first, _, service = fixture_account(platform)
    original = start_selection(service, account, [first])
    worker = Worker(config)
    if claimed:
        worker.claim()
    worker.recover()
    row = service.learning.snapshot(account)
    assert row["state"] == row["desired_state"] == "paused"
    assert row["revision"] > original["revision"]
    assert row["selected_course_ids"] == [first]
    assert worker.claim() is None
    service.learning.action(account, "resume", row["revision"])
    assert worker.claim()["kind"] == "study"


@pytest.mark.parametrize("old_state,desired", [("running", "paused"), ("paused", "paused"), ("stopping", "stopped")])
def test_upgrade_migrates_latest_selection_and_preserves_history(platform, old_state, desired):
    _, app, _, account, first, second, service = fixture_account(platform)
    first_task = service.queue(account, "study", first)
    second_task = service.queue(account, "study", second)
    db = app.state.db
    db.execute("UPDATE tasks SET state='paused',updated_at=1 WHERE id=?", (first_task["id"],))
    db.execute("UPDATE tasks SET state=?,updated_at=2 WHERE id=?", (old_state, second_task["id"]))
    db.log("历史 Console 输出", second_task["id"], source="yatori")
    db.execute("DELETE FROM schema_migrations WHERE version=4")
    Database(db.path)
    row = service.learning.snapshot(account)
    assert row["selected_course_ids"] == [second]
    assert row["desired_state"] == desired
    assert db.one("SELECT COUNT(*) AS n FROM tasks")["n"] == 2
    assert db.one("SELECT message FROM logs WHERE source='yatori'")["message"] == "历史 Console 输出"


def test_removed_courses_preserve_history_and_pause_invalid_selection(platform):
    config, app, _, account, first, second, service = fixture_account(platform)
    start_selection(service, account, [first, second])
    service.save_courses(account, [{"courseId": "100", "clazzId": "200", "title": "课程一"}], authoritative=True)
    # Apply the authoritative result as a query completion would do.
    app.state.db.execute("UPDATE tasks SET state='stopped' WHERE account_id=?", (account,))
    worker = Worker(config)
    assert worker.claim() is None
    row = service.learning.snapshot(account)
    assert row["state"] == "failed" and row["desired_state"] == "paused"
    assert row["selected_course_ids"] == [first, second]
    assert row["courses"][1]["available"] is False
    assert app.state.db.one("SELECT COUNT(*) AS n FROM tasks")["n"] == 1


def test_review_fingerprint_rejects_changed_rules_and_foreign_courses(platform):
    _, app, client, account, first, _, service = fixture_account(platform)
    row = service.learning.save(account, [first], 0)
    fingerprint = service.study_plan(account)["fingerprint"]
    app.state.db.set_setting("study", service.study_settings(account) | {"work": True})
    url = f"/api/accounts/{account}/learning"
    assert client.post(url + "/action", json={"action": "start", "revision": row["revision"], "fingerprint": fingerprint}).status_code == 409
    other = add_account(client, "另一账号")
    foreign = add_course(app, other)
    assert client.put(url, json={"course_ids": [foreign], "revision": row["revision"]}).status_code == 409
    assert app.state.db.rows("SELECT * FROM tasks") == []


def test_refresh_during_query_stop_returns_conflict_then_can_restart(platform):
    config, _, client, account, _, _, service = fixture_account(platform)
    service.learning.action(account, "refresh")
    worker = Worker(config)
    query = worker.claim()
    row = service.learning.action(account, "stop")
    response = client.post(f"/api/accounts/{account}/learning/action", json={"action": "refresh", "revision": row["revision"]})
    assert response.status_code == 409
    worker.finish(query, "stopped", "同步已停止")
    assert service.learning.action(account, "refresh")["refresh_pending"]


@pytest.mark.parametrize("operation", ["selection", "refresh"])
def test_delayed_launch_preserves_accepted_rule_snapshot(platform, operation):
    config, app, _, account, first, second, service = fixture_account(platform)
    start_selection(service, account, [first])
    worker = Worker(config)
    old = worker.claim()
    row = service.learning.snapshot(account)
    if operation == "selection":
        service.learning.save(account, [second], row["revision"])
    else:
        service.learning.action(account, "refresh", row["revision"])
    app.state.db.set_setting("study", service.study_settings(account) | {"answer_mode": "chaoxing_ai", "submit_mode": "submit", "work": True})
    worker.finish(old, "stopped", "进程已停止")
    next_task = worker.claim()
    if operation == "refresh":
        worker.finish(next_task, "failed", "同步失败")
        next_task = worker.claim()
    options = json.loads(next_task["checkpoint"])["options"]
    assert options["answer_mode"] == "off" and options["submit_mode"] == "save" and options["work"] is False


@pytest.mark.parametrize("fails", [False, True])
def test_course_refresh_reports_only_target_and_preserves_other_progress(platform, fails):
    config, _, client, account, first, second, service = fixture_account(platform)
    service.save_chapters(first, [{"id": "1", "title": "一"}, {"id": "2", "title": "二", "has_finished": True}])
    service.save_chapters(second, [{"id": "1", "title": "已完成", "has_finished": True}])
    before = service.learning.snapshot(account)
    calls = []
    class Process:
        failing = fails
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            control()
            calls.append((mode, course["courseId"]))
            if self.failing:
                raise ConsoleError("该课程进度查询失败")
            return [{"id": "1", "title": "一", "has_finished": True}, {"id": "2", "title": "二", "has_finished": True}]
    url = f"/api/courses/{first}/sync"
    assert client.post(url).status_code == 200
    queued = client.get(f"/api/accounts/{account}/learning").json()
    assert queued["courses"][0]["progress_refresh_state"] == "queued"
    assert queued["courses"][1]["progress_refresh_state"] is None
    assert client.post(url).status_code == 409
    worker = Worker(config, Process)
    worker.run_task(worker.claim())
    result = service.learning.snapshot(account)
    assert calls == [("chapters", "100")]
    assert result["courses"][1] == before["courses"][1]
    assert result["courses"][0]["progress_refresh_state"] == ("failed" if fails else "succeeded")
    assert result["courses"][0]["progress"] == (50 if fails else 100)
    if fails:
        assert result["courses"][0]["progress_synced_at"] == before["courses"][0]["progress_synced_at"]
        assert result["courses"][0]["progress_refresh_message"] == "该课程进度查询失败"
        Process.failing = False
        assert client.post(url).status_code == 200
        worker.run_task(worker.claim())
        assert service.learning.snapshot(account)["courses"][0]["progress_refresh_state"] == "succeeded"


def test_sync_course_list_keeps_chapter_progress_untouched(platform):
    config, _, client, account, first, second, service = fixture_account(platform)
    service.save_chapters(first, [{"id": "1", "title": "已完成", "has_finished": True}])
    before = service.learning.snapshot(account)
    calls = []
    class Process:
        def __init__(self, _): pass
        def run(self, account_id, value, proxy, secrets, control, log, mode, course):
            calls.append(mode)
            assert mode == "courses" and course is None
            return [{"courseId": "100", "clazzId": "200", "title": "课程一"}, {"courseId": "101", "clazzId": "201", "title": "课程二"}]
    assert client.post(f"/api/accounts/{account}/sync").status_code == 200
    assert service.learning.snapshot(account)["courses_refresh_state"] == "queued"
    worker = Worker(config, Process)
    worker.run_task(worker.claim())
    result = service.learning.snapshot(account)
    assert result["courses_refresh_state"] == "succeeded" and calls == ["courses"]
    for old, current in zip(before["courses"], result["courses"]):
        assert current["progress"] == old["progress"]
        assert current["progress_synced_at"] == old["progress_synced_at"]
        assert current["progress_refresh_state"] is None
