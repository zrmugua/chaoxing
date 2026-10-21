"""Durable queue and lifecycle management for original Console processes."""
import json
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from filelock import FileLock, Timeout
from .config import Config
from .console_process import ConsoleProcess, ConsoleError, console_config
from .db import Database
from .security import Vault
from .services import PlatformService


class TaskInterrupted(Exception):
    def __init__(self, state):
        self.state = state


class Worker:
    def __init__(self, config: Config, process_factory=ConsoleProcess):
        self.config = config
        self.db = Database(config.data_dir / "console.sqlite3")
        self.vault = (config.vault_factory or Vault)(config.master_key)
        marker = self.db.one("SELECT value FROM settings WHERE key='vault_check'")
        if marker:
            self.vault.open(json.loads(marker["value"]))
        self.service = PlatformService(self.db, self.vault)
        self.process_factory = process_factory
        self.shutdown = threading.Event()

    def recover(self):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            c.execute("UPDATE tasks SET state='paused',updated_at=?,message='服务重启，点击继续可重新启动 Console' WHERE state IN ('running','pausing','recovering')", (now,))
            c.execute("UPDATE tasks SET state='stopped',updated_at=?,finished_at=? WHERE state='stopping'", (now, now))
            c.execute("UPDATE runs SET state='interrupted',finished_at=?,message='Console 管理服务已中断' WHERE finished_at IS NULL", (now,))
        for path in (self.config.data_dir / "console").glob("*/*"):
            if path.name in ("config.yaml", "query.json", "query-result.json", "ip.txt"):
                path.unlink(missing_ok=True)
        self.db.log("原版 Console 进程管理服务已启动")

    def claim(self, available_slots=8):
        if available_slots < 1:
            return None
        now = time.time()
        with self.db.connect(immediate=True) as c:
            row = c.execute("""SELECT * FROM tasks t WHERE t.state IN ('queued','recovering') AND t.next_run_at<=?
                AND NOT EXISTS(SELECT 1 FROM tasks busy WHERE busy.account_id=t.account_id
                AND busy.state IN ('running','pausing','stopping')) ORDER BY t.id LIMIT 1""", (now,)).fetchone()
            if row is None:
                return None
            c.execute("UPDATE tasks SET state='running',attempts=attempts+1,started_at=COALESCE(started_at,?),finished_at=NULL,updated_at=? WHERE id=?", (now, now, row["id"]))
            run_id = c.execute("INSERT INTO runs(task_id,attempt,started_at,state) VALUES(?,?,?,'running')", (row["id"], row["attempts"] + 1, now)).lastrowid
            return dict(row) | {"attempts": row["attempts"] + 1, "run_id": run_id}

    def control(self, task_id):
        if self.shutdown.is_set():
            raise TaskInterrupted("paused")
        current = self.db.one("SELECT state FROM tasks WHERE id=?", (task_id,))
        if not current or current["state"] in ("stopping", "stopped"):
            raise TaskInterrupted("stopped")
        if current["state"] in ("pausing", "paused"):
            raise TaskInterrupted("paused")

    def finish(self, task, state, message, confirmed=False):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            current = c.execute("SELECT state FROM tasks WHERE id=?", (task["id"],)).fetchone()
            if not current:
                return
            if current["state"] in ("pausing", "stopping"):
                state = "paused" if current["state"] == "pausing" else "stopped"
                message = "Console 进程已暂停" if state == "paused" else "Console 进程已停止"
                confirmed = False
            c.execute("UPDATE tasks SET state=?,message=?,updated_at=?,finished_at=?,progress=?,server_state=? WHERE id=?",
                      (state, message, now, None if state == "paused" else now, 100 if confirmed else 0,
                       "confirmed" if confirmed else "unknown", task["id"]))
            c.execute("UPDATE runs SET state=?,message=?,finished_at=? WHERE id=?", (state, message, now, task["run_id"]))
        self.db.log(message, task["id"], "error" if state == "failed" else "info")

    def run_task(self, task):
        try:
            self.control(task["id"])
            account = self.service.account(task["account_id"])
            checkpoint = json.loads(task["checkpoint"])
            if checkpoint.get("runtime") != "original-console":
                raise ConsoleError("请从账号或课程页确认配置并创建 Console 任务")
            rules = checkpoint.get("options") or self.service.study_settings(account["id"])
            value, proxy, secrets = console_config(self.service, account, rules, checkpoint.get("course_titles") if task["kind"] == "study" else None)
            mode = {"login": "courses", "sync_courses": "courses", "sync_chapters": "chapters", "sync_assessments": "assessments"}.get(task["kind"])
            course = self.vault.open(self.service.course(task["course_id"])["payload"]) if mode in ("chapters", "assessments") else None
            if not mode and task["kind"] != "study":
                raise ConsoleError("该任务类型需要重新创建")
            self.db.log("正在启动 yatori-go-console" + (" 查询" if mode else ""), task["id"])
            result = self.process_factory(self.config).run(account["id"], value, proxy, secrets,
                lambda: self.control(task["id"]),
                lambda text, level: self.db.log(text, task["id"], level, source="yatori"), mode, course)
            self.control(task["id"])
            if mode == "courses":
                self.service.save_courses(account["id"], result)
                self.db.execute("UPDATE accounts SET status='ready',checked_at=? WHERE id=?", (time.time(), account["id"]))
                message = f"Console 查询完成，共 {len(result)} 门课程"
            elif mode == "chapters":
                self.service.save_chapters(task["course_id"], result)
                message = f"Console 查询完成，共 {len(result)} 个章节"
            elif mode == "assessments":
                self.service.save_assessments(task["course_id"], result)
                message = f"Console 查询完成，共 {len(result)} 项作业与考试"
            else:
                message = "Console 执行结束；结果请查看原始日志，课程进度可通过同步查询"
            self.finish(task, "succeeded" if mode else "completed", message, confirmed=bool(mode))
        except TaskInterrupted as error:
            self.finish(task, error.state, "Console 进程已暂停；继续时会重新启动" if error.state == "paused" else "Console 进程已停止")
        except ConsoleError as error:
            self.finish(task, "failed", str(error))
        except Exception:
            self.finish(task, "failed", "Console 管理任务异常，请检查配置与设备存储空间")

    def tick(self):
        self.db.execute("INSERT INTO runtime VALUES(1,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat", (time.time(),))

    def serve(self):
        try:
            with FileLock(self.config.data_dir / "worker.lock", timeout=0):
                self.recover()
                futures = set()
                last_cleanup = 0
                with ThreadPoolExecutor(max_workers=8, thread_name_prefix="console-account") as pool:
                    while not self.shutdown.is_set():
                        self.tick()
                        futures = {f for f in futures if not f.done()}
                        for _ in range(max(0, self.db.settings()["concurrency"] - len(futures))):
                            task = self.claim()
                            if task is None:
                                break
                            futures.add(pool.submit(self.run_task, task))
                        if time.time() - last_cleanup > 3600:
                            self.db.execute("DELETE FROM logs WHERE created_at<?", (time.time() - self.db.settings()["log_retention_days"] * 86400,))
                            last_cleanup = time.time()
                        self.shutdown.wait(0.5)
                self.db.execute("DELETE FROM runtime WHERE id=1")
        except Timeout:
            raise RuntimeError("该数据目录已有 Console 管理服务运行") from None


def main():
    os.umask(0o077)
    worker = Worker(Config.from_env())
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: worker.shutdown.set())
    worker.serve()


if __name__ == "__main__":
    main()
