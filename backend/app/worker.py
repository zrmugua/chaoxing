"""Single scheduler with durable claims and one running task per account."""
import json
import math
import os
import signal
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, CancelledError

from filelock import FileLock, Timeout

from .adapters.yatori import YatoriAdapter
from .adapters.contracts import AdapterError
from .config import Config
from .db import Database
from .security import Vault
from .services import PlatformService
from .learning import rules_with_defaults, job_enabled, task_slots
from .notifications import notify_task
from .assessment_worker import AssessmentWorker


class TaskInterrupted(Exception):
    def __init__(self, state):
        self.state = state


class Worker(AssessmentWorker):
    def __init__(self, config: Config, adapter_factory=YatoriAdapter):
        self.config = config
        self.db = Database(config.data_dir / "console.sqlite3")
        self.vault = (config.vault_factory or Vault)(config.master_key)
        marker = self.db.one("SELECT value FROM settings WHERE key='vault_check'")
        if marker:
            self.vault.open(json.loads(marker["value"]))
        self.service = PlatformService(self.db, self.vault)
        self.adapter_factory = adapter_factory
        self.shutdown = threading.Event()

    def recover(self):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            c.execute("UPDATE tasks SET state='recovering',updated_at=?,message='服务重启，等待核对服务端状态' WHERE state='running'", (now,))
            c.execute("UPDATE tasks SET state='paused',updated_at=? WHERE state='pausing'", (now,))
            c.execute("UPDATE tasks SET state='stopped',updated_at=?,finished_at=? WHERE state='stopping'", (now, now))
            c.execute("UPDATE runs SET state='interrupted',finished_at=?,message='后台进程中断，等待状态核对' WHERE finished_at IS NULL", (now,))
        self.db.log("后台调度器已启动，恢复检查完成")

    def claim(self, available_slots=8):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            row = c.execute("""SELECT * FROM tasks t WHERE t.state IN ('queued','recovering') AND t.next_run_at<=?
                              AND NOT EXISTS(SELECT 1 FROM tasks busy WHERE busy.account_id=t.account_id
                              AND busy.state IN ('running','pausing','stopping')
                              AND NOT (t.kind='study' AND busy.kind='study'
                                AND EXISTS(SELECT 1 FROM accounts a WHERE a.id=t.account_id AND a.cookies IS NOT NULL)
                                AND COALESCE(json_extract(t.checkpoint,'$.options.video_mode'),'normal')='multi_course'
                                AND COALESCE(json_extract(busy.checkpoint,'$.options.video_mode'),'normal')='multi_course'))
                              AND CASE WHEN t.kind='study' AND json_extract(t.checkpoint,'$.options.video_mode')='multi_node'
                                THEN COALESCE(json_extract(t.checkpoint,'$.options.node_concurrency'),2)+1 ELSE 1 END <= ?
                              ORDER BY t.id LIMIT 1""", (now, available_slots)).fetchone()
            if row is None:
                return None
            c.execute("UPDATE tasks SET state='running',attempts=attempts+1,started_at=COALESCE(started_at,?),finished_at=NULL,updated_at=? WHERE id=?",
                      (now, now, row["id"]))
            run_id = c.execute("INSERT INTO runs(task_id,attempt,started_at,state) VALUES(?,?,?,'running')",
                               (row["id"], row["attempts"] + 1, now)).lastrowid
            task = dict(row)
            task["attempts"] += 1
            task["run_id"] = run_id
            return task

    def control(self, task_id):
        if self.shutdown.is_set():
            raise TaskInterrupted("recovering")
        current = self.db.one("SELECT state FROM tasks WHERE id=?", (task_id,))
        if not current:
            raise TaskInterrupted("stopped")
        if current["state"] in ("pausing", "paused"):
            raise TaskInterrupted("paused")
        if current["state"] in ("stopping", "stopped"):
            raise TaskInterrupted("stopped")

    def update(self, task_id, **fields):
        fields["updated_at"] = time.time()
        keys = list(fields)
        self.db.execute("UPDATE tasks SET " + ",".join(key + "=?" for key in keys) + " WHERE id=?",
                        tuple(fields[k] for k in keys) + (task_id,))

    def checkpoint(self, task_id, checkpoint):
        self.update(task_id, checkpoint=json.dumps(checkpoint, ensure_ascii=False))

    def create_adapter(self, task, credentials, cookies, control):
        if self.adapter_factory is YatoriAdapter or getattr(self.adapter_factory, "func", None) is YatoriAdapter:
            account = self.db.one("SELECT label FROM accounts WHERE id=?", (task["account_id"],))
            credentials = credentials | {"log_level": self.db.settings()["log_level"],
                                         "log_label": account["label"] if account else ""}
            return self.adapter_factory(credentials, cookies, control,
                log_callback=lambda text, level: self.db.log(text, task["id"], level, source="yatori"))
        return self.adapter_factory(credentials, cookies, control)

    def finish(self, task, state, message, server_state=None):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            current = c.execute("SELECT state FROM tasks WHERE id=?", (task["id"],)).fetchone()
            if not current:
                return
            if current["state"] == "pausing":
                state, message = "paused", "任务已暂停"
            elif current["state"] == "stopping":
                state, message = "stopped", "任务已停止"
            terminal = state not in ("queued", "recovering", "paused")
            c.execute("UPDATE tasks SET state=?,message=?,updated_at=?,finished_at=? WHERE id=?",
                      (state, message, now, now if terminal else None, task["id"]))
            if server_state:
                c.execute("UPDATE tasks SET server_state=? WHERE id=?", (server_state, task["id"]))
            c.execute("UPDATE runs SET state=?,message=?,finished_at=? WHERE id=?", (state, message, now, task["run_id"]))
        self.db.log(message, task["id"], "error" if state == "failed" else "info")
        try:
            notify_task(self.service, task, state, message)
        except (AdapterError, ValueError):
            self.db.log("任务结果已保存，邮件通知发送失败，请检查邮件配置", task["id"], "warning")

    def run_task(self, task):
        adapter = None
        account = self.db.one("SELECT * FROM accounts WHERE id=?", (task["account_id"],))
        try:
            self.control(task["id"])
            if not account:
                raise AdapterError("account_missing", "账号记录不存在")
            credentials = self.vault.open(account["credentials"])
            options = rules_with_defaults(json.loads(task["checkpoint"]).get("options"))
            credentials = credentials | {key: options[key] for key in ("execution_timeout", "media_client")}
            credentials["proxy_url"] = self.service.account_preferences(account["id"], True)["proxy_url"]
            cookies = self.vault.open(account["cookies"]) if account["cookies"] else []
            adapter = self.create_adapter(task, credentials, cookies, lambda: self.control(task["id"]))
            self.db.log("已建立本任务独立的 Yatori 执行进程", task["id"], "debug")
            if task["kind"] == "login" or not cookies:
                adapter.login(credentials["username"], credentials["password"])
                self.save_cookies(account["id"], adapter)
            if task["kind"] in ("login", "sync_courses"):
                courses = adapter.list_courses()
                self.service.save_courses(account["id"], courses)
                self.update(task["id"], progress=100)
                self.finish(task, "succeeded", f"登录验证与课程同步完成，共 {len(courses)} 门课程", "confirmed")
            else:
                row = self.db.one("SELECT * FROM courses WHERE id=? AND account_id=?", (task["course_id"], account["id"]))
                if not row:
                    raise AdapterError("course_missing", "课程记录不存在")
                course = self.vault.open(row["payload"])
                if task["kind"] == "sync_assessments":
                    items = adapter.list_assessments(course)
                    self.service.save_assessments(row["id"],items)
                    self.save_cookies(account["id"],adapter)
                    self.update(task["id"],progress=100)
                    self.finish(task,"succeeded",f"作业与考试列表已同步，共 {len(items)} 项","confirmed")
                    return
                chapters = adapter.list_chapters(course)
                self.service.save_chapters(row["id"], chapters)
                self.save_cookies(account["id"], adapter)
                if task["kind"] == "sync_chapters":
                    self.update(task["id"], progress=100)
                    self.finish(task, "succeeded", f"章节同步完成，共 {len(chapters)} 个章节", "confirmed")
                else:
                    self.study(task, course, chapters, adapter)
            self.save_cookies(account["id"], adapter)
        except TaskInterrupted as error:
            self.finish(task, error.state, {"paused": "任务已暂停", "stopped": "任务已停止", "recovering": "任务已保存，等待后台恢复"}[error.state])
        except AdapterError as error:
            self.integration_error(task, account, error)
        except Exception:
            self.finish(task, "failed", "后台执行异常，已保留检查点，请检查配置与兼容性")
        finally:
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    self.db.log("适配进程清理异常，请检查后台进程状态", task["id"], "error")

    def save_cookies(self, account_id, adapter):
        self.db.execute("UPDATE accounts SET cookies=?,status='ready',checked_at=? WHERE id=?",
                        (self.vault.seal(adapter.export_cookies()), time.time(), account_id))

    def integration_error(self, task, account, error):
        manual_codes = {"manual_required", "captcha", "forbidden", "auth_required", "login_failed", "session_expired"}
        if error.code in manual_codes:
            if account:
                self.db.execute("UPDATE accounts SET status='attention',checked_at=? WHERE id=?", (time.time(), account["id"]))
            self.finish(task, "waiting_manual", str(error))
        elif error.retryable and task["attempts"] < task["max_attempts"]:
            checkpoint = json.loads(self.db.one("SELECT checkpoint FROM tasks WHERE id=?", (task["id"],))["checkpoint"])
            state = "recovering" if checkpoint.get("pending") else "queued"
            delay = min(self.db.settings()["retry_seconds"] * 2 ** (task["attempts"] - 1), 3600)
            self.update(task["id"], next_run_at=time.time() + delay)
            self.finish(task, state, f"接口暂时不可用，将在 {delay} 秒后核对重试")
        else:
            self.finish(task, "failed", str(error))

    def study(self, task, course, chapters, adapter):
        checkpoint = json.loads(task["checkpoint"])
        options = rules_with_defaults(checkpoint.get("options"))
        pending = checkpoint.setdefault("pending", {})
        checkpoint_lock = threading.RLock()
        manual, unconfirmed, filtered = False, False, False
        checkpoint["options"] = options
        if options["shuffle"]:
            chapters = list(chapters)
            random.SystemRandom().shuffle(chapters)
        if not chapters:
            self.finish(task, "awaiting_confirmation", "章节列表为空，等待核对课程状态", "unknown")
            return
        for index, chapter in enumerate(chapters):
            self.control(task["id"])
            if chapter.get("has_finished") is True:
                prefix = str(chapter["id"]) + ":"
                for key in list(pending):
                    if key.startswith(prefix):
                        pending.pop(key)
                self.checkpoint(task["id"], checkpoint)
                continue
            if chapter.get("need_unlock"):
                manual = True
                continue
            self.db.log(f"读取第 {index + 1}/{len(chapters)} 个章节的任务点", task["id"])
            jobs = adapter.list_jobs(course, chapter)
            # Console nodeRun executes media and documents before chapter tests.
            order = {"video": 0, "audio": 0, "document": 1, "read": 1,
                     "workid": 2, "work": 2, "quiz": 2, "hyperlink": 3}
            jobs.sort(key=lambda job: order.get(job.kind, 4))
            if options["shuffle"]:
                random.SystemRandom().shuffle(jobs)
            self.db.log(f"读取到 {len(jobs)} 个任务点", task["id"])
            if not jobs and not chapter.get("has_finished"):
                unconfirmed = True
            parallel_jobs = []
            for job in jobs:
                self.control(task["id"])
                key = str(chapter["id"]) + ":" + job.id
                if job.passed:
                    pending.pop(key, None)
                    self.checkpoint(task["id"], checkpoint)
                    continue
                if not job_enabled(job.kind, options):
                    filtered = True
                    self.db.log(f"按学习规则保留 {job.kind} 任务点", task["id"])
                    continue
                if job.metadata.get("completion_unknown") is True:
                    unconfirmed = True
                    self.db.log("任务点完成状态缺少依据，保留待确认状态", task["id"])
                    continue
                # A missing confirmation after interruption is resolved by server readback.
                position = job.metadata.get("playTime")
                resume_video = job.kind in ("video", "audio") and type(position) in (int, float) and math.isfinite(position) and position >= 0
                if key in pending and not resume_video:
                    unconfirmed = True
                    continue
                if job.kind in ("workid", "work", "quiz"):
                    if parallel_jobs:
                        if not self.parallel_points(task, course, chapter, parallel_jobs, checkpoint, checkpoint_lock, options):
                            unconfirmed = True
                        parallel_jobs = []
                    if options["answer_mode"] != "off":
                        if key in checkpoint.get("papers", {}):
                            manual = True
                            continue
                        paper = adapter.chapter_paper(course, job)
                        if paper.get("passed"):
                            pending.pop(key, None)
                            self.checkpoint(task["id"], checkpoint)
                            continue
                        self.remember_questions(task, str(chapter["id"]), job.id, paper["questions"])
                        result = self.answer_paper(task, course, paper, adapter, checkpoint, key)
                        if not result["submitted"]:
                            manual = True
                        elif not any(j.id == job.id and j.passed for j in adapter.list_jobs(course, chapter)):
                            unconfirmed = True
                        continue
                    questions = adapter.questions(course, job)
                    self.db.execute("""INSERT INTO question_sets(course_id,chapter_id,job_id,payload,updated_at)
                                      VALUES(?,?,?,?,?) ON CONFLICT(course_id,chapter_id,job_id) DO UPDATE SET
                                      payload=excluded.payload,updated_at=excluded.updated_at""",
                                    (task["course_id"], str(chapter["id"]), job.id, self.vault.seal(questions), time.time()))
                    manual = True
                    self.db.log("章节测验已解析，请在课程详情查看题目并在学习通确认提交", task["id"])
                    continue
                if job.kind not in ("video", "audio", "document", "read", "hyperlink"):
                    manual = True
                    self.db.log("发现需要人工处理的任务类型", task["id"])
                    continue
                if options["video_mode"] == "multi_node":
                    parallel_jobs.append(job)
                    continue
                if not self.execute_point(task, course, chapter, job, adapter, checkpoint, checkpoint_lock,
                    lambda ratio: self.update(task["id"], progress=min(99, (index + min(1, max(0, ratio))) / len(chapters) * 100))):
                    unconfirmed = True
            if parallel_jobs:
                if not self.parallel_points(task, course, chapter, parallel_jobs, checkpoint, checkpoint_lock, options):
                    unconfirmed = True
            self.update(task["id"], progress=min(99, (index + 1) / len(chapters) * 100))
        assessment_manual, assessment_unconfirmed = self.study_assessments(task, course, adapter, checkpoint)
        fresh_chapters = adapter.list_chapters(course)
        self.service.save_chapters(task["course_id"], fresh_chapters)
        if fresh_chapters and all(c.get("has_finished") is True for c in fresh_chapters) and not assessment_manual and not assessment_unconfirmed:
            self.checkpoint(task["id"], checkpoint | {"pending": {}})
            self.update(task["id"], progress=100)
            self.finish(task, "succeeded", "课程章节已获学习通服务端完成确认", "confirmed")
        elif manual or assessment_manual:
            self.finish(task, "waiting_manual", "学习任务已处理，请在学习通核对保存的试卷或受限任务", "pending")
        elif filtered and not unconfirmed and not assessment_unconfirmed:
            self.update(task["id"], progress=100)
            self.finish(task, "succeeded", "所选任务已处理，课程仍有学习规则保留的任务点", "pending")
        else:
            self.finish(task, "awaiting_confirmation", "本地执行已结束，请同步核对学习通服务端进度", "pending" if unconfirmed else "unknown")

    def execute_point(self, task, course, chapter, job, adapter, checkpoint, lock, progress, control=None):
        control = control or (lambda: self.control(task["id"]))
        control()
        key = str(chapter["id"]) + ":" + job.id
        with lock:
            previous = checkpoint["pending"].get(key)
            checkpoint["pending"][key] = {"kind": job.kind, "sent_at": time.time()}
            self.checkpoint(task["id"], checkpoint)

        def restore_unsent():
            with lock:
                if previous is None:
                    checkpoint["pending"].pop(key, None)
                else:
                    checkpoint["pending"][key] = previous
                self.checkpoint(task["id"], checkpoint)

        self.db.log(f"开始执行 {job.kind} 任务点", task["id"])
        try:
            control()
        except BaseException:
            restore_unsent()
            raise
        try:
            adapter.execute(course, job, control, progress)
        except BaseException as error:
            if getattr(error, "rpc_request_sent", None) is False:
                restore_unsent()
            raise
        self.save_cookies(task["account_id"], adapter)
        fresh = adapter.list_jobs(course, chapter)
        confirmed = any(j.id == job.id and j.passed for j in fresh)
        with lock:
            if confirmed:
                checkpoint["pending"].pop(key, None)
            self.checkpoint(task["id"], checkpoint)
        self.db.log("任务点已获服务端确认" if confirmed else "本地执行结束，等待服务端状态确认", task["id"])
        return confirmed

    def parallel_points(self, task, course, chapter, jobs, checkpoint, lock, options):
        """Each concurrent point owns a fresh native account process and canonical card state."""
        account = self.db.one("SELECT * FROM accounts WHERE id=?", (task["account_id"],))
        credentials = self.vault.open(account["credentials"]) | {key: options[key] for key in ("execution_timeout", "media_client")}
        credentials["proxy_url"] = self.service.account_preferences(account["id"], True)["proxy_url"]
        cookies = self.vault.open(account["cookies"]) if account["cookies"] else []
        cancelled = threading.Event()
        first_error = []

        def cancel(error):
            with lock:
                if not first_error:
                    first_error.append(error)
                cancelled.set()

        def control():
            if cancelled.is_set():
                raise CancelledError()
            self.control(task["id"])

        def execute(job):
            child = None
            try:
                control()
                child = self.create_adapter(task, credentials, cookies, control)
                current = next((item for item in child.list_jobs(course, chapter) if item.id == job.id), None)
                if current is None:
                    raise AdapterError("parser_changed", "任务点刷新后无法定位，请同步核对")
                if current.passed:
                    with lock:
                        checkpoint["pending"].pop(str(chapter["id"])+":"+job.id, None)
                        self.checkpoint(task["id"], checkpoint)
                    return True
                if current.metadata.get("completion_unknown"):
                    return False
                position = current.metadata.get("playTime")
                with lock:
                    was_pending = str(chapter["id"])+":"+job.id in checkpoint["pending"]
                if was_pending and not (current.kind in ("video", "audio") and type(position) in (int,float) and math.isfinite(position) and position >= 0):
                    return False
                return self.execute_point(task, course, chapter, current, child, checkpoint, lock, lambda _: None, control)
            except Exception as error:
                cancel(error)
                raise
            finally:
                if child is not None:
                    try:
                        child.close()
                    except Exception as error:
                        cancel(error)
                        raise

        with ThreadPoolExecutor(max_workers=options["node_concurrency"], thread_name_prefix="task-point") as pool:
            futures = [pool.submit(execute, job) for job in jobs]
            results = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as error:
                    cancel(error)
            if first_error:
                raise first_error[0]
            return all(results)

    def tick(self):
        self.db.execute("INSERT INTO runtime VALUES(1,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat", (time.time(),))

    def serve(self):
        lock = FileLock(self.config.data_dir / "worker.lock", timeout=0)
        try:
            with lock:
                self.recover()
                futures = {}
                last_cleanup = 0
                with ThreadPoolExecutor(max_workers=8, thread_name_prefix="account") as pool:
                    while not self.shutdown.is_set():
                        self.tick()
                        futures = {f: slots for f, slots in futures.items() if not f.done()}
                        capacity = self.db.settings()["concurrency"] - len(futures)
                        for _ in range(max(0, capacity)):
                            task = self.claim(8 - sum(futures.values()))
                            if task is None:
                                break
                            futures[pool.submit(self.run_task, task)] = task_slots(task)
                        if time.time() - last_cleanup > 3600:
                            self.db.execute("DELETE FROM logs WHERE created_at<?", (time.time() - self.db.settings()["log_retention_days"] * 86400,))
                            last_cleanup = time.time()
                        self.shutdown.wait(0.5)
                self.db.execute("DELETE FROM runtime WHERE id=1")
        except Timeout:
            raise RuntimeError("该数据目录已有后台调度器运行") from None


def main():
    os.umask(0o077)
    worker = Worker(Config.from_env())
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: worker.shutdown.set())
    worker.serve()


if __name__ == "__main__":
    main()
