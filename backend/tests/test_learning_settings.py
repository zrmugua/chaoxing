import json
import threading
import time
from concurrent.futures import CancelledError

import httpx
import pytest

from backend.app.adapters.contracts import AdapterError, Job
from backend.app.ai import preview_answer
from backend.app.learning import DEFAULT_RULES
from backend.app.notifications import notify_task
from backend.app.services import PlatformService
from backend.app.worker import Worker
from backend.tests.test_platform import platform, add_account, add_course, RecordingAdapter, study_setup


def test_account_rules_inherit_override_and_reset_independently(platform):
    config, app, client = platform
    first, second = add_account(client, "甲"), add_account(client, "乙")
    rules = DEFAULT_RULES | {"video_mode": "off", "include_courses": ["100"]}
    assert client.put("/api/settings/study", json=rules).status_code == 200
    assert client.get(f"/api/accounts/{first}/study-settings").json()["rules"]["video_mode"] == "off"
    override = rules | {"video_mode": "normal", "audio": False}
    assert client.put(f"/api/accounts/{first}/study-settings", json=override).json()["overridden"]
    assert client.get(f"/api/accounts/{second}/study-settings").json()["rules"]["audio"]
    reset = client.delete(f"/api/accounts/{first}/study-settings").json()
    assert not reset["overridden"] and reset["rules"]["audio"]
    assert client.get("/api/accounts/9999/study-settings").status_code == 404


def test_batch_course_selection_and_task_snapshot(platform):
    config, app, client = platform
    account = add_account(client)
    first = add_course(app, account)
    service = PlatformService(app.state.db, app.state.vault)
    service.save_courses(account, [{"courseId":"101","clazzId":"201","cpi":"fixture", "title":"第二门课程"}])
    rules = DEFAULT_RULES | {"include_courses":["100", "101"], "exclude_courses":["101"], "media_client":"mobile"}
    client.put("/api/settings/study", json=rules)
    result = client.post(f"/api/accounts/{account}/study").json()
    assert result["selected"] == 1 and result["tasks"][0]["course_id"] == first
    assert client.post(f"/api/accounts/{account}/study").json()["skipped"] == 1
    client.put("/api/settings/study", json=DEFAULT_RULES)
    task = app.state.db.one("SELECT * FROM tasks")
    assert json.loads(task["checkpoint"])["options"]["media_client"] == "mobile"


def test_disabled_task_type_never_executes_or_confirms_course(platform):
    config, app, client = platform
    client.put("/api/settings/study", json=DEFAULT_RULES | {"document":False})
    class Disabled(RecordingAdapter):
        writes = 0
    worker, task = study_setup(platform, Disabled)
    worker.run_task(task)
    record = worker.db.one("SELECT state,server_state FROM tasks")
    assert Disabled.writes == 0
    assert record == {"state":"succeeded", "server_state":"pending"}


def test_execution_settings_reach_account_engine(platform):
    config, app, client = platform
    client.put("/api/settings/study", json=DEFAULT_RULES | {"media_client":"mobile", "execution_timeout":120})
    captured = {}
    class Capture(RecordingAdapter):
        def __init__(self, credentials, cookies, control):
            super().__init__(credentials,cookies,control)
            captured.update(credentials)
    worker, task = study_setup(platform, Capture)
    worker.run_task(task)
    assert captured["media_client"] == "mobile" and captured["execution_timeout"] == 120


def test_sensitive_service_settings_are_encrypted_and_kept_on_blank_update(platform, monkeypatch):
    config, app, client = platform
    monkeypatch.setattr("backend.app.settings_routes.validate_endpoint", lambda _: None)
    monkeypatch.setattr("backend.app.settings_routes.validate_email", lambda _: None)
    bank = {"enabled":True,"url":"https://bank.example/query", "token":"fixture-bank-secret", "ai_fallback":True}
    assert client.put("/api/settings/question-bank", json=bank).status_code == 200
    del bank["token"]
    assert client.put("/api/settings/question-bank", json=bank).json()["secret_configured"]
    email = {"enabled":True, "host":"smtp.example", "sender":"sender@example.com",
             "recipients":["me@example.com"], "password":"fixture-mail-secret"}
    assert client.put("/api/settings/email", json=email).status_code == 200
    service = PlatformService(app.state.db, app.state.vault)
    assert service.secret_settings("question_bank",True)["token"] == "fixture-bank-secret"
    for name, secret in (("question_bank","fixture-bank-secret"),("email","fixture-mail-secret")):
        assert secret not in app.state.db.one("SELECT value FROM settings WHERE key=?",(name,))["value"]
        assert secret not in str(client.get("/api/settings/"+name.replace("_","-")).json())
    settings = client.get("/api/settings").json()
    assert "email" not in settings and "question_bank" not in settings


@pytest.mark.parametrize("style", ["chat", "responses"])
def test_ai_protocols_use_correct_body_and_parse_response(monkeypatch, style):
    monkeypatch.setattr("backend.app.ai.validate_endpoint",lambda _:None)
    real = httpx.Client
    def handler(request):
        body = json.loads(request.content)
        assert ("input" if style == "responses" else "messages") in body
        assert request.url.path.endswith("/responses" if style=="responses" else "/chat/completions")
        if style == "responses":
            return httpx.Response(200,json={"output":[{"content":[{"type":"output_text","text":"Answer"}]}]})
        return httpx.Response(200,json={"choices":[{"message":{"content":"Answer"}}]})
    monkeypatch.setattr("backend.app.ai.httpx.Client",lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    assert preview_answer({"enabled":True,"base_url":"https://ai.example/v1","api_key":"fixture", "model":"test", "api_style":style},"Question",[]) == "Answer"


def test_custom_question_bank_protocol_and_ai_fallback(platform,monkeypatch):
    config, app, client = platform
    monkeypatch.setattr("backend.app.settings_routes.validate_endpoint",lambda _:None)
    monkeypatch.setattr("backend.app.question_bank.validate_endpoint",lambda _:None)
    client.put("/api/settings/question-bank",json={"enabled":True,"url":"https://bank.example/query","token":"fixture","ai_fallback":True})
    real = httpx.Client
    calls = []
    def handler(request):
        body=json.loads(request.content)
        assert body["content"] == "Question" and len(body["md5"])==32
        assert request.headers["Authorization"] == "Bearer fixture"
        calls.append(body)
        return httpx.Response(200,json={"code":200,"data":{"answers":["First","Second"]}})
    monkeypatch.setattr("backend.app.question_bank.httpx.Client",lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    result=client.post("/api/answers/preview",json={"question":"Question","options":["A","B"]})
    assert result.json()["source"]=="question_bank" and result.json()["answer"]=="First\nSecond"
    def empty_bank(*args):
        raise AdapterError("bank_empty", "empty")
    monkeypatch.setattr("backend.app.question_bank.lookup",empty_bank)
    monkeypatch.setattr("backend.app.question_bank.preview_answer",lambda *args:"AI result")
    assert client.post("/api/answers/preview",json={"question":"Question"}).json()["source"]=="ai"


def test_smtp_tls_and_event_selection(platform, monkeypatch):
    config, app, client = platform
    monkeypatch.setattr("backend.app.notifications.validate_email",lambda _:None)
    events=[]
    class SMTP:
        def __init__(self,*args,**kwargs): events.append("connect")
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def starttls(self,**kwargs): events.append("tls")
        def login(self,*args): events.append("login")
        def send_message(self,message): events.append(message["Subject"])
    monkeypatch.setattr("backend.app.notifications.smtplib.SMTP",SMTP)
    service = PlatformService(app.state.db,app.state.vault)
    email=service.secret_settings("email",True) | {"enabled":True,"security":"starttls","host":"smtp.example","port":587,
        "username":"test","password":"fixture","sender":"a@example.com","recipients":["b@example.com"],"on_success":False}
    app.state.db.set_setting("email",app.state.vault.seal(email))
    notify_task(service,{"kind":"study","id":1},"succeeded","done")
    assert events==[]
    notify_task(service,{"kind":"study","id":1},"failed","failure")
    assert events[:3]==["connect","tls","login"]


def test_external_endpoints_reject_unsafe_destination(platform):
    config, app, client = platform
    assert client.put("/api/settings/question-bank",json={"enabled":True,"url":"http://127.0.0.1"}).status_code==422
    assert client.put("/api/settings/email",json={"enabled":True,"host":"smtp.example","sender":"bad\nheader","recipients":[]}).status_code==422


def test_multi_course_mode_allows_distinct_course_tasks_and_serializes_login(platform):
    config, app, client=platform
    account=add_account(client)
    first=add_course(app,account)
    service=PlatformService(app.state.db,app.state.vault)
    app.state.db.execute("UPDATE accounts SET cookies=? WHERE id=?", (app.state.vault.seal([{"name":"_uid","value":"42","domain":".chaoxing.com"}]),account))
    service.save_courses(account,[{"courseId":"101","clazzId":"201","cpi":"fixture","title":"Second"}])
    second=app.state.db.one("SELECT id FROM courses WHERE remote_id='101'")["id"]
    client.put("/api/settings/study",json=DEFAULT_RULES | {"video_mode":"multi_course"})
    service.queue(account,"study",first);service.queue(account,"study",second);service.queue(account,"login")
    worker=Worker(config)
    assert worker.claim()["kind"]=="study"
    assert worker.claim()["kind"]=="study"
    assert worker.claim() is None


def test_multi_course_bootstrap_waits_for_first_saved_session(platform):
    config, app, client=platform
    account=add_account(client)
    add_course(app,account)
    service=PlatformService(app.state.db,app.state.vault)
    service.save_courses(account,[{"courseId":"101","clazzId":"201","cpi":"fixture","title":"Second"}])
    client.put("/api/settings/study",json=DEFAULT_RULES | {"video_mode":"multi_course"})
    service.queue_courses(account)
    worker=Worker(config)
    assert worker.claim() is not None
    assert worker.claim() is None
    app.state.db.execute("UPDATE accounts SET cookies=? WHERE id=?",(app.state.vault.seal([{"name":"_uid","value":"42","domain":".chaoxing.com"}]),account))
    assert worker.claim() is not None


def test_parallel_points_use_distinct_sessions_and_retain_server_confirmation(platform):
    config, app, client=platform
    client.put("/api/settings/study",json=DEFAULT_RULES | {"video_mode":"multi_node","node_concurrency":2})
    barrier=threading.Barrier(2, timeout=5)
    completed=set()
    identities=[]
    lock=threading.Lock()
    class Concurrent(RecordingAdapter):
        def list_jobs(self,course,chapter):
            with lock:
                return [Job(name,"300","document",name,name in completed,0,{}, {}) for name in ("first","second")]
        def execute(self,course,job,control,progress):
            control()
            with lock:
                identities.append(id(self))
            barrier.wait()
            with lock:
                completed.add(job.id)
        def list_chapters(self,course):
            return [{"id":"300","title":"Chapter","jobCount":2,"has_finished":len(completed)==2}]
    worker,task=study_setup(platform,Concurrent)
    worker.run_task(task)
    assert len(set(identities))==2
    assert completed=={"first","second"}
    row=worker.db.one("SELECT * FROM tasks")
    assert row["state"]=="succeeded" and row["server_state"]=="confirmed"
    assert not json.loads(row["checkpoint"])["pending"]


def test_task_point_resource_budget_includes_parent_session(platform):
    config, app, client=platform
    account=add_account(client)
    course=add_course(app,account)
    client.put("/api/settings/study",json=DEFAULT_RULES | {"video_mode":"multi_node","node_concurrency":3})
    service=PlatformService(app.state.db,app.state.vault)
    service.queue(account,"study",course)
    worker=Worker(config)
    assert worker.claim(3) is None
    assert worker.claim(4)["course_id"]==course


def test_assessment_sync_task_keeps_query_status_separate_from_course_completion(platform):
    config,app,client=platform
    account=add_account(client)
    course=add_course(app,account)
    class Lists(RecordingAdapter):
        def list_assessments(self,course,work=True,exam=True):
            return [{"id":"501","kind":"exam","title":"Exam","status":"未开始","remaining":"2 days"}]
    assert client.post(f"/api/courses/{course}/assessments/sync").status_code==200
    worker=Worker(config,Lists)
    worker.run_task(worker.claim())
    items=client.get(f"/api/courses/{course}/assessments").json()
    assert items[0]["status"]=="未开始"
    assert not app.state.db.rows("SELECT * FROM chapters WHERE confirmed=1")
    assert app.state.db.one("SELECT state FROM tasks")["state"]=="succeeded"


def test_log_threshold_filters_records_and_keeps_redaction(platform):
    config,app,client=platform
    client.put("/api/settings",json={"concurrency":2,"retry_seconds":30,"max_attempts":3,"log_retention_days":30,"log_level":"warning"})
    before=app.state.db.one("SELECT COUNT(*) n FROM logs")["n"]
    app.state.db.log("filtered-info")
    app.state.db.log("password=fixture-secret",level="warning")
    assert app.state.db.one("SELECT COUNT(*) n FROM logs")["n"]==before+1
    row=app.state.db.one("SELECT * FROM logs ORDER BY id DESC LIMIT 1")
    assert "fixture-secret" not in row["message"]


def test_unrecognized_assessment_response_keeps_previous_records(platform):
    config,app,client=platform
    account=add_account(client)
    course=add_course(app,account)
    service=PlatformService(app.state.db,app.state.vault)
    service.save_assessments(course,[{"id":"known","kind":"exam","title":"Exam","status":"未开始","remaining":"2 days"}])
    class Changed(RecordingAdapter):
        def list_assessments(self,course,work=True,exam=True):
            raise AdapterError("parser_changed","列表结构变化")
    client.post(f"/api/courses/{course}/assessments/sync")
    worker=Worker(config,Changed)
    worker.run_task(worker.claim())
    assert app.state.db.one("SELECT state FROM tasks")["state"]=="failed"
    assert client.get(f"/api/courses/{course}/assessments").json()[0]["remote_id"]=="known"


def test_manual_challenge_stops_queued_task_points(platform):
    config,app,client=platform
    client.put("/api/settings/study",json=DEFAULT_RULES | {"video_mode":"multi_node","node_concurrency":1})
    executed=[]
    class Challenge(RecordingAdapter):
        def list_jobs(self,course,chapter):
            return [Job(name,"300","document",name,False,0,{}, {}) for name in ("first","second","third")]
        def execute(self,course,job,control,progress):
            control()
            executed.append(job.id)
            raise AdapterError("manual_required","需要人工验证")
    worker,task=study_setup(platform,Challenge)
    worker.run_task(task)
    assert executed==["first"]
    assert app.state.db.one("SELECT state FROM tasks")["state"]=="waiting_manual"


def test_manual_challenge_cancels_running_peer_and_keeps_trigger_error(platform):
    config,app,client=platform
    client.put("/api/settings/study",json=DEFAULT_RULES | {"video_mode":"multi_node","node_concurrency":2})
    started=threading.Event()
    ended=threading.Event()
    class Challenge(RecordingAdapter):
        def list_jobs(self,course,chapter):
            return [Job(name,"300","video",name,False,0,{"playTime":0}, {}) for name in ("first","second")]
        def execute(self,course,job,control,progress):
            if job.id=="first":
                assert started.wait(timeout=3)
                raise AdapterError("manual_required","需要人工验证")
            started.set()
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    control()
                    time.sleep(.01)
                pytest.fail("peer execution did not stop")
            finally:
                ended.set()
    worker,task=study_setup(platform,Challenge)
    worker.run_task(task)
    assert ended.is_set()
    record=app.state.db.one("SELECT state,message FROM tasks")
    assert record["state"]=="waiting_manual" and "需要人工验证" in record["message"]


@pytest.mark.parametrize("phase",["before_execute","before_rpc_send"])
def test_cancel_before_request_restores_unsubmitted_point(platform,phase):
    called=[]
    class Unsent(RecordingAdapter):
        def execute(self,*args):
            called.append(True)
            error=CancelledError()
            error.rpc_request_sent=False
            raise error
    worker,task=study_setup(platform,Unsent)
    checkpoint={"pending":{}}
    calls=0
    def control():
        nonlocal calls
        calls+=1
        if calls==2 and phase=="before_execute":
            raise CancelledError()
    job=Job("doc","300","document","Document",False,0,{}, {})
    adapter=Unsent({},[],control)
    with pytest.raises(CancelledError):
        worker.execute_point(task,{}, {"id":"300"},job,adapter,checkpoint,threading.RLock(),lambda _:None,control)
    assert not checkpoint["pending"]
    assert bool(called)==(phase=="before_rpc_send")
