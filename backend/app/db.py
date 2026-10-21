import contextlib
import json
import sqlite3
import time
from logging.handlers import RotatingFileHandler
from logging import LogRecord
from filelock import FileLock
from pathlib import Path

from .security import redact


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY CHECK(id=1), username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(client TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, label TEXT NOT NULL, credentials TEXT NOT NULL,
 cookies TEXT, status TEXT NOT NULL DEFAULT 'new', checked_at REAL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 remote_id TEXT NOT NULL, clazz_id TEXT NOT NULL, title TEXT NOT NULL, teacher TEXT NOT NULL, payload TEXT NOT NULL,
 synced_at REAL NOT NULL, UNIQUE(account_id, remote_id, clazz_id));
CREATE TABLE IF NOT EXISTS chapters(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
 remote_id TEXT NOT NULL, title TEXT NOT NULL, job_count INTEGER NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
 locked INTEGER NOT NULL DEFAULT 0, synced_at REAL NOT NULL, UNIQUE(course_id, remote_id));
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE, kind TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
 server_state TEXT NOT NULL DEFAULT 'unknown', progress REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 3, next_run_at REAL NOT NULL DEFAULT 0, checkpoint TEXT NOT NULL DEFAULT '{}',
 message TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL, started_at REAL, finished_at REAL);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_task ON tasks(account_id, COALESCE(course_id,0),kind)
 WHERE state IN ('queued','running','pausing','stopping','recovering');
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 attempt INTEGER NOT NULL, started_at REAL NOT NULL, finished_at REAL, state TEXT NOT NULL, message TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
 level TEXT NOT NULL, message TEXT NOT NULL, created_at REAL NOT NULL, source TEXT NOT NULL DEFAULT 'console');
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_rules(account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS account_preferences(account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY,course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
 remote_id TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL,remaining TEXT NOT NULL,
 synced_at REAL NOT NULL,UNIQUE(course_id,kind,remote_id));
CREATE TABLE IF NOT EXISTS runtime(id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL NOT NULL);
CREATE TABLE IF NOT EXISTS account_learning(account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
 selected_course_ids TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 0, execution_rules TEXT,
 desired_state TEXT NOT NULL DEFAULT 'stopped', state TEXT NOT NULL DEFAULT 'idle', message TEXT NOT NULL DEFAULT '',
 current_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL, active_course_titles TEXT NOT NULL DEFAULT '[]',
 latest_activity TEXT, refresh_pending INTEGER NOT NULL DEFAULT 0, refresh_error TEXT, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS question_sets(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
 chapter_id TEXT NOT NULL, job_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at REAL NOT NULL,
 UNIQUE(course_id,chapter_id,job_id));
CREATE INDEX IF NOT EXISTS tasks_queue ON tasks(state, next_run_at);
INSERT OR IGNORE INTO schema_migrations VALUES(1, unixepoch());
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(logs)")}
            if "source" not in columns:
                conn.execute("ALTER TABLE logs ADD COLUMN source TEXT NOT NULL DEFAULT 'console'")
            conn.execute("CREATE INDEX IF NOT EXISTS logs_task_cursor ON logs(task_id,id)")
            conn.execute("CREATE INDEX IF NOT EXISTS logs_source_cursor ON logs(source,id)")
            conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2, unixepoch())")
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE version=3").fetchone():
                now = time.time()
                conn.execute("UPDATE tasks SET state='stopped',updated_at=?,finished_at=?,message='已升级 Console 运行方式，请从账号或课程页确认配置后重新启动' WHERE state IN ('queued','running','pausing','stopping','recovering','paused')", (now, now))
                conn.execute("UPDATE runs SET state='interrupted',finished_at=? WHERE finished_at IS NULL", (now,))
                conn.execute("INSERT INTO schema_migrations VALUES(3,?)", (now,))
            course_columns = {row["name"] for row in conn.execute("PRAGMA table_info(courses)")}
            if "progress_synced_at" not in course_columns:
                conn.execute("ALTER TABLE courses ADD COLUMN progress_synced_at REAL")
                conn.execute("UPDATE courses SET progress_synced_at=(SELECT MAX(synced_at) FROM chapters WHERE course_id=courses.id)")
            if "available" not in course_columns:
                conn.execute("ALTER TABLE courses ADD COLUMN available INTEGER NOT NULL DEFAULT 1")
            if "execution_rules" not in {row["name"] for row in conn.execute("PRAGMA table_info(account_learning)")}:
                conn.execute("ALTER TABLE account_learning ADD COLUMN execution_rules TEXT")
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE version=4").fetchone():
                now = time.time()
                for account in conn.execute("SELECT id FROM accounts").fetchall():
                    task = conn.execute("SELECT * FROM tasks WHERE account_id=? AND kind='study' AND state IN ('queued','running','pausing','stopping','recovering','paused') ORDER BY updated_at DESC,id DESC LIMIT 1", (account["id"],)).fetchone()
                    selected = []
                    if task:
                        checkpoint = json.loads(task["checkpoint"])
                        titles = checkpoint.get("course_titles", [])
                        courses = conn.execute("SELECT id,title FROM courses WHERE account_id=? ORDER BY id", (account["id"],)).fetchall()
                        selected = [course["id"] for course in courses if course["id"] in checkpoint.get("selected_course_ids", []) or (course["id"] == task["course_id"] if task["course_id"] else course["title"] in titles)]
                    state = "stopped" if task and task["state"] == "stopping" else "paused" if task else "idle"
                    conn.execute("INSERT OR IGNORE INTO account_learning(account_id,selected_course_ids,desired_state,state,message,updated_at) VALUES(?,?,?,?,?,?)",
                                 (account["id"], json.dumps(selected), "paused" if state == "paused" else "stopped", state, "课程选择已保留" if task else "", now))
                    if task:
                        conn.execute("UPDATE account_learning SET execution_rules=? WHERE account_id=?", (json.dumps(checkpoint.get("options")) if checkpoint.get("options") else None, account["id"]))
                conn.execute("UPDATE tasks SET state=CASE WHEN state='stopping' THEN 'stopped' ELSE 'paused' END,updated_at=?,message='课程选择已保留，可从账号页继续学习' WHERE kind='study' AND state IN ('queued','running','pausing','stopping','recovering')", (now,))
                conn.execute("UPDATE runs SET state='interrupted',finished_at=? WHERE finished_at IS NULL AND task_id IN (SELECT id FROM tasks WHERE kind='study')", (now,))
                conn.execute("INSERT INTO schema_migrations VALUES(4,?)", (now,))

    @contextlib.contextmanager
    def connect(self, immediate=False):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            if immediate:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, sql, args=()):
        with self.connect() as c:
            return [dict(row) for row in c.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as c:
            return c.execute(sql, args).lastrowid

    def log(self, message, task_id=None, level="info", source="console"):
        ranks = {"debug": 0, "info": 1, "warning": 2, "error": 3}
        if source != "yatori" and ranks.get(level.lower(), 1) < ranks[self.settings()["log_level"]]:
            return
        message = redact(message, limit=66000 if source == "yatori" else 1000)
        self.execute("INSERT INTO logs(task_id,level,message,created_at,source) VALUES(?,?,?,?,?)",
                     (task_id, level, message, time.time(), source))
        if self.settings()["log_out_file"]:
            try:
                with FileLock(str(self.path.parent / "log-output.lock"), timeout=2):
                    handler = RotatingFileHandler(self.path.parent / "console.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
                    try:
                        handler.emit(LogRecord("console", 20, "", 0, f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] [{source}] [任务 #{task_id}] {message}", (), None))
                    finally:
                        handler.close()
            except (OSError, TimeoutError):
                pass

    def settings(self):
        defaults = {"concurrency": 2, "retry_seconds": 30, "max_attempts": 3, "log_retention_days": 30, "log_level": "info",
                    "completion_tone": False, "color_log": True, "log_out_file": False}
        defaults.update({r["key"]: json.loads(r["value"]) for r in self.rows("SELECT * FROM settings") if r["key"] in defaults})
        return defaults

    def set_setting(self, key, value):
        self.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, json.dumps(value, ensure_ascii=False)))
