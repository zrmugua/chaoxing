import json
import hashlib
import sqlite3
import time

from fastapi import HTTPException

from .db import Database
from .security import Vault
from .learning import rules_with_defaults, course_selected


ACTIVE = ("queued", "running", "pausing", "stopping", "recovering")
EXECUTING = ("running", "pausing", "stopping")


class PlatformService:
    def __init__(self, db: Database, vault: Vault):
        self.db = db
        self.vault = vault

    def account(self, account_id):
        account = self.db.one("SELECT * FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise HTTPException(404, "账号不存在")
        return account

    def course(self, course_id):
        course = self.db.one("SELECT * FROM courses WHERE id=?", (course_id,))
        if not course:
            raise HTTPException(404, "课程不存在")
        return course

    def queue(self, account_id, kind, course_id=None, options=None, selected_courses=None):
        self.account(account_id)
        if course_id is not None and self.course(course_id)["account_id"] != account_id:
            raise HTTPException(409, "课程与账号归属不一致")
        now = time.time()
        checkpoint = {"runtime": "original-console"}
        if kind == "study":
            rules = rules_with_defaults(options if options is not None else self.study_settings(account_id))
            courses = self.db.rows("SELECT id,title,remote_id FROM courses WHERE account_id=? ORDER BY id", (account_id,))
            selected = list(selected_courses) if selected_courses is not None else [c for c in courses if (c["id"] == course_id if course_id is not None else course_selected(c, rules))]
            if selected_courses is not None and any(c not in courses for c in selected):
                raise HTTPException(409, "课程已更新，请重新查看启动摘要")
            if not selected:
                raise HTTPException(409, "请同步并选择课程后启动")
            titles = {c["title"] for c in selected}
            if any(c["title"] in titles and c not in selected for c in courses):
                raise HTTPException(409, "原版 Console 按课程名称筛选，请同时选择同名课程")
            checkpoint.update(options=rules, course_titles=sorted(titles))
        try:
            task_id = self.db.execute(
                "INSERT INTO tasks(account_id,course_id,kind,created_at,updated_at,max_attempts,checkpoint) VALUES(?,?,?,?,?,?,?)",
                (account_id, course_id, kind, now, now, self.db.settings()["max_attempts"], json.dumps(checkpoint)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "同类任务已在队列中") from None
        self.db.log(f"任务 #{task_id} 已加入队列", task_id)
        return self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))

    def action(self, task_id, action):
        now = time.time()
        try:
            with self.db.connect(immediate=True) as c:
                row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
                if row is None:
                    raise HTTPException(404, "任务不存在")
                state = row["state"]
                if action in ("resume", "retry") and json.loads(row["checkpoint"]).get("runtime") != "original-console":
                    raise HTTPException(409, "此为升级前任务，请从账号或课程页确认配置后重新启动")
                if action == "pause" and state in ("queued", "recovering", "running"):
                    next_state = "pausing" if state == "running" else "paused"
                elif action == "stop" and state in (*ACTIVE, "paused", "waiting_manual", "awaiting_confirmation"):
                    next_state = "stopping" if state in EXECUTING else "stopped"
                elif action == "resume" and state == "paused":
                    next_state = "queued"
                elif action == "retry" and state in ("failed", "waiting_manual", "awaiting_confirmation", "stopped"):
                    next_state = "recovering"
                    c.execute("UPDATE tasks SET attempts=0 WHERE id=?", (task_id,))
                else:
                    raise HTTPException(409, "当前任务状态不支持该操作")
                c.execute("UPDATE tasks SET state=?, updated_at=?, finished_at=NULL, next_run_at=0, message=? WHERE id=?",
                          (next_state, now, "等待后台处理", task_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "相同账号和课程已有同类任务，请先处理该任务") from None
        self.db.log(f"任务 #{task_id}：{action}", task_id)
        return self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))

    def ai_settings(self, reveal=False):
        row = self.db.one("SELECT value FROM settings WHERE key='ai'")
        config = self.vault.open(json.loads(row["value"])) if row else {
            "enabled": False, "base_url": "https://api.openai.com/v1", "model": "", "api_key": "", "api_style": "chat"}
        config.setdefault("api_style", "chat")
        if reveal:
            return config
        return {k: v for k, v in config.items() if k != "api_key"} | {"key_configured": bool(config.get("api_key"))}

    def study_settings(self, account_id=None):
        if account_id is not None:
            self.account(account_id)
            row = self.db.one("SELECT payload FROM learning_rules WHERE account_id=?", (account_id,))
            if row:
                return rules_with_defaults(json.loads(row["payload"]))
        row = self.db.one("SELECT value FROM settings WHERE key='study'")
        return rules_with_defaults(json.loads(row["value"]) if row else None)

    def account_preferences(self, account_id, reveal=False):
        self.account(account_id)
        row = self.db.one("SELECT payload FROM account_preferences WHERE account_id=?", (account_id,))
        value = {"inform_emails": [], "proxy_url": ""} | (self.vault.open(row["payload"]) if row else {})
        return value if reveal else {"inform_emails": value["inform_emails"], "proxy_configured": bool(value["proxy_url"])}

    def study_plan(self, account_id, course_id=None):
        rules = self.study_settings(account_id)
        courses = self.db.rows("SELECT id,title,remote_id FROM courses WHERE account_id=? ORDER BY id", (account_id,))
        selected = [course for course in courses if (course["id"] == course_id if course_id else course_selected(course, rules))]
        if rules["answer_mode"] == "ai" and not self.ai_settings()["enabled"]:
            raise HTTPException(409, "请在系统设置中启用 AI 答题服务")
        if rules["answer_mode"] == "ai" and self.ai_settings()["api_style"] == "responses":
            raise HTTPException(409, "请将 AI 接口设置为 Chat Completions 或秘塔协议")
        if rules["answer_mode"] == "question_bank" and not self.secret_settings("question_bank")["enabled"]:
            raise HTTPException(409, "请在系统设置中启用题库服务")
        fingerprint = hashlib.sha256(json.dumps({"rules": rules, "courses": selected}, sort_keys=True).encode()).hexdigest()
        return {"rules": rules, "courses": selected, "count": len(selected), "fingerprint": fingerprint,
                "will_submit": rules["answer_mode"] != "off" and rules["submit_mode"] != "save"}

    def queue_courses(self, account_id, plan=None):
        rules = plan["rules"] if plan else self.study_settings(account_id)
        courses = self.db.rows("SELECT id,title,remote_id FROM courses WHERE account_id=? ORDER BY id", (account_id,))
        selected = list(plan["courses"]) if plan else [course for course in courses if course_selected(course, rules)]
        if not selected:
            raise HTTPException(409, "请同步并选择课程后启动")
        task = self.queue(account_id, "study", options=rules, selected_courses=selected)
        return {"tasks": [task], "selected": len(selected), "skipped": 0}

    def secret_settings(self, name, reveal=False):
        defaults = {
            "question_bank": {"enabled": False, "url": "", "token": "", "ai_fallback": False, "allow_lan": False},
            "email": {"enabled": False, "host": "", "port": 465, "security": "ssl", "username": "",
                      "password": "", "sender": "", "recipients": [], "on_success": True,
                      "on_failure": True, "on_attention": True},
        }[name]
        row = self.db.one("SELECT value FROM settings WHERE key=?", (name,))
        value = defaults | (self.vault.open(json.loads(row["value"])) if row else {})
        if reveal:
            return value
        secret = "token" if name == "question_bank" else "password"
        return {k: v for k, v in value.items() if k != secret} | {"secret_configured": bool(value[secret])}

    def save_courses(self, account_id, courses):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            for course in courses:
                c.execute("""INSERT INTO courses(account_id,remote_id,clazz_id,title,teacher,payload,synced_at)
                             VALUES(?,?,?,?,?,?,?) ON CONFLICT(account_id,remote_id,clazz_id) DO UPDATE SET
                             title=excluded.title,teacher=excluded.teacher,payload=excluded.payload,synced_at=excluded.synced_at""",
                          (account_id, str(course["courseId"]), str(course["clazzId"]), course["title"],
                           course.get("teacher", ""), self.vault.seal(course), now))

    def save_chapters(self, course_id, chapters):
        now = time.time()
        with self.db.connect(immediate=True) as c:
            for chapter in chapters:
                c.execute("""INSERT INTO chapters(course_id,remote_id,title,job_count,confirmed,locked,synced_at)
                             VALUES(?,?,?,?,?,?,?) ON CONFLICT(course_id,remote_id) DO UPDATE SET
                             title=excluded.title,job_count=excluded.job_count,confirmed=excluded.confirmed,
                             locked=excluded.locked,synced_at=excluded.synced_at""",
                          (course_id, str(chapter["id"]), chapter["title"], int(chapter.get("jobCount", 0)),
                           int(chapter.get("has_finished", False)), int(chapter.get("need_unlock", False)), now))

    def save_assessments(self, course_id, items, kinds=("work", "exam")):
        with self.db.connect(immediate=True) as connection:
            for kind in kinds:
                connection.execute("DELETE FROM assessments WHERE course_id=? AND kind=?", (course_id,kind))
            for item in items:
                if item["kind"] not in kinds:
                    continue
                connection.execute("INSERT INTO assessments(course_id,remote_id,kind,title,status,remaining,synced_at) VALUES(?,?,?,?,?,?,?)",
                    (course_id,item["id"],item["kind"],item["title"],item["status"],item["remaining"],time.time()))
