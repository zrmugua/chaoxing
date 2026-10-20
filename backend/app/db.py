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
 level TEXT NOT NULL, message TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_rules(account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS account_preferences(account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY,course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
 remote_id TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL,remaining TEXT NOT NULL,
 synced_at REAL NOT NULL,UNIQUE(course_id,kind,remote_id));
CREATE TABLE IF NOT EXISTS runtime(id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL NOT NULL);
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

    def log(self, message, task_id=None, level="info"):
        ranks = {"debug": 0, "info": 1, "warning": 2, "error": 3}
        if ranks.get(level.lower(), 1) < ranks[self.settings()["log_level"]]:
            return
        self.execute("INSERT INTO logs(task_id,level,message,created_at) VALUES(?,?,?,?)",
                     (task_id, level, redact(message), time.time()))
        if self.settings()["log_out_file"]:
            try:
                with FileLock(str(self.path.parent / "log-output.lock"), timeout=2):
                    handler = RotatingFileHandler(self.path.parent / "console.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
                    try:
                        handler.emit(LogRecord("console", 20, "", 0, f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {redact(message)}", (), None))
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
