"""Persistent account intent, reconciled through the Console execution queue."""
import json
import time

from fastapi import HTTPException


EXECUTING = ("running", "pausing", "stopping")
PENDING = ("queued", "recovering")


class AccountLearning:
    def __init__(self, service):
        self.service = service
        self.db = service.db

    def ensure(self, connection, account_id):
        if not connection.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(404, "账号不存在")
        connection.execute("INSERT OR IGNORE INTO account_learning(account_id,updated_at) VALUES(?,?)", (account_id, time.time()))
        return dict(connection.execute("SELECT * FROM account_learning WHERE account_id=?", (account_id,)).fetchone())

    def snapshot(self, account_id):
        with self.db.connect(immediate=True) as connection:
            row = self.ensure(connection, account_id)
            account = dict(connection.execute("SELECT id,label,status,checked_at,created_at FROM accounts WHERE id=?", (account_id,)).fetchone())
            courses = [dict(course) for course in connection.execute("""SELECT c.id,c.account_id,c.remote_id,c.clazz_id,c.title,c.teacher,c.synced_at,c.progress_synced_at,c.available,
                COUNT(ch.id) AS chapter_count,COALESCE(SUM(ch.confirmed),0) AS confirmed_chapters
                FROM courses c LEFT JOIN chapters ch ON ch.course_id=c.id WHERE c.account_id=? GROUP BY c.id ORDER BY c.id""", (account_id,))]
            task = connection.execute("SELECT * FROM tasks WHERE id=?", (row["current_task_id"],)).fetchone()
            heartbeat = connection.execute("SELECT heartbeat FROM runtime WHERE id=1").fetchone()
        for course in courses:
            course["available"] = bool(course["available"])
            course["progress"] = round(100 * course["confirmed_chapters"] / course["chapter_count"], 1) if course["progress_synced_at"] is not None and course["chapter_count"] else None
        running_titles = []
        if task and task["kind"] == "study" and task["state"] in EXECUTING:
            running_titles = json.loads(task["checkpoint"]).get("course_titles", [])
        return {"account": account, "courses": courses, "selected_course_ids": json.loads(row["selected_course_ids"]),
                "revision": row["revision"], "state": row["state"], "desired_state": row["desired_state"],
                "message": row["message"], "worker_online": bool(heartbeat and time.time() - heartbeat["heartbeat"] < 20),
                "current_task_id": row["current_task_id"], "running_course_titles": running_titles,
                "active_course_titles": json.loads(row["active_course_titles"]) if running_titles else [],
                "latest_activity": json.loads(row["latest_activity"]) if row["latest_activity"] else None,
                "refresh_pending": bool(row["refresh_pending"]), "refresh_error": row["refresh_error"]}

    def validate_selection(self, connection, account_id, course_ids):
        selected_ids = list(dict.fromkeys(course_ids))
        courses = [dict(row) for row in connection.execute("SELECT id,title,remote_id FROM courses WHERE account_id=? AND available=1 ORDER BY id", (account_id,))]
        selected = [course for course in courses if course["id"] in selected_ids]
        if len(selected) != len(selected_ids):
            raise HTTPException(409, "课程列表已更新，请刷新后重新选择")
        titles = {course["title"] for course in selected}
        if any(course["title"] in titles and course["id"] not in selected_ids for course in courses):
            raise HTTPException(409, "原版 Console 按课程名称筛选，请同时选择同名课程")
        return selected

    def validate_revision(self, row, revision):
        if revision is not None and revision != row["revision"]:
            raise HTTPException(409, "账号学习设置已更新，请刷新后重试")

    def validate_plan(self, account_id, fingerprint, course_id=None):
        plan = self.service.study_plan(account_id, course_id)
        if fingerprint is not None and fingerprint != plan["fingerprint"]:
            raise HTTPException(409, "学习规则或课程已更新，请重新查看启动摘要")
        return plan["rules"]

    def save(self, account_id, course_ids, revision, fingerprint=None):
        with self.db.connect(immediate=True) as connection:
            row = self.ensure(connection, account_id)
            self.validate_revision(row, revision)
            self.validate_selection(connection, account_id, course_ids)
            if row["desired_state"] == "running" and course_ids:
                rules = self.validate_plan(account_id, fingerprint)
                connection.execute("UPDATE account_learning SET execution_rules=? WHERE account_id=?", (json.dumps(rules), account_id))
            desired = row["desired_state"] if course_ids else "stopped"
            connection.execute("UPDATE account_learning SET selected_course_ids=?,revision=revision+1,desired_state=?,message=?,updated_at=? WHERE account_id=?",
                               (json.dumps(list(dict.fromkeys(course_ids))), desired, "课程选择已保存", time.time(), account_id))
            self.reconcile(connection, account_id)
        return self.snapshot(account_id)

    def action(self, account_id, action, revision=None, fingerprint=None):
        with self.db.connect(immediate=True) as connection:
            row = self.ensure(connection, account_id)
            self.validate_revision(row, revision)
            if action in ("start", "resume"):
                selected = self.validate_selection(connection, account_id, json.loads(row["selected_course_ids"]))
                if not selected:
                    raise HTTPException(409, "请先选择需要学习的课程")
                rules = self.validate_plan(account_id, fingerprint)
                connection.execute("UPDATE account_learning SET execution_rules=? WHERE account_id=?", (json.dumps(rules), account_id))
                desired, state, message = "running", "queued", "正在准备学习"
            elif action in ("pause", "stop"):
                desired = "paused" if action == "pause" else "stopped"
                state, message = desired, "学习已暂停" if action == "pause" else "学习已停止"
                connection.execute("UPDATE tasks SET state=CASE WHEN state IN ('running','pausing','stopping') THEN 'stopping' ELSE 'stopped' END,updated_at=? WHERE account_id=? AND kind!='study' AND state IN ('queued','recovering','running','pausing','stopping')", (time.time(), account_id))
                connection.execute("UPDATE account_learning SET refresh_pending=0 WHERE account_id=?", (account_id,))
            elif action == "refresh":
                desired, state, message = row["desired_state"], "refreshing", "正在同步课程与章节进度"
                if connection.execute("SELECT 1 FROM tasks WHERE account_id=? AND kind='refresh_account' AND state IN ('pausing','stopping')", (account_id,)).fetchone():
                    raise HTTPException(409, "正在停止上一轮同步，请稍后刷新进度")
                existing = connection.execute("SELECT id FROM tasks WHERE account_id=? AND kind='refresh_account' AND state IN ('queued','running','recovering')", (account_id,)).fetchone()
                if not existing:
                    self.insert_task(connection, account_id, "refresh_account", {"runtime": "original-console", "account_refresh": True})
                connection.execute("UPDATE account_learning SET refresh_pending=1,refresh_error=NULL WHERE account_id=?", (account_id,))
            else:
                raise HTTPException(422, "学习操作无效")
            connection.execute("UPDATE account_learning SET revision=revision+1,desired_state=?,state=?,message=?,updated_at=? WHERE account_id=?", (desired, state, message, time.time(), account_id))
            self.reconcile(connection, account_id)
        return self.snapshot(account_id)

    def insert_task(self, connection, account_id, kind, checkpoint):
        now = time.time()
        return connection.execute("INSERT INTO tasks(account_id,kind,checkpoint,created_at,updated_at) VALUES(?,?,?,?,?)", (account_id, kind, json.dumps(checkpoint, ensure_ascii=False), now, now)).lastrowid

    def reconcile(self, connection, account_id):
        row = dict(connection.execute("SELECT * FROM account_learning WHERE account_id=?", (account_id,)).fetchone())
        tasks = [dict(task) for task in connection.execute("SELECT * FROM tasks WHERE account_id=? AND state IN ('queued','recovering','running','pausing','stopping') ORDER BY id", (account_id,))]
        queries = [task for task in tasks if task["kind"] != "study"]
        now = time.time()
        for task in tasks:
            if task["kind"] != "study":
                continue
            checkpoint = json.loads(task["checkpoint"])
            obsolete = (not checkpoint.get("account_managed") or checkpoint.get("revision") != row["revision"] or row["desired_state"] != "running" or queries)
            if obsolete:
                if row["desired_state"] == "paused":
                    state = "pausing" if task["state"] in EXECUTING else "paused"
                else:
                    state = "stopping" if task["state"] in EXECUTING else "stopped"
                connection.execute("UPDATE tasks SET state=?,updated_at=?,finished_at=CASE WHEN ?='stopped' THEN ? ELSE finished_at END,message=? WHERE id=?", (state, now, state, now, "正在应用账号学习设置", task["id"]))
                task["state"] = state
        executing = next((task for task in tasks if task["state"] in EXECUTING), None)
        if executing:
            if executing["kind"] != "study":
                state, message = ("refreshing", "正在同步课程信息") if executing["state"] == "running" else ("stopping", "正在停止查询进程")
            elif executing["state"] in ("pausing", "stopping"):
                state = "applying" if row["desired_state"] == "running" else "pausing" if row["desired_state"] == "paused" else "stopping"
                message = "正在应用课程选择" if state == "applying" else "正在暂停学习" if state == "pausing" else "正在停止学习"
            else:
                state, message = "running", "Console 正在执行学习"
            connection.execute("UPDATE account_learning SET state=?,message=?,current_task_id=?,updated_at=? WHERE account_id=?", (state, message, executing["id"], now, account_id))
            return
        if queries:
            connection.execute("UPDATE account_learning SET state='refreshing',message='等待同步课程信息',current_task_id=?,active_course_titles='[]',updated_at=? WHERE account_id=?", (queries[0]["id"], now, account_id))
            return
        if row["desired_state"] == "running":
            pending = next((task for task in tasks if task["kind"] == "study" and task["state"] in PENDING), None)
            if pending:
                task_id = pending["id"]
            else:
                try:
                    selected = self.validate_selection(connection, account_id, json.loads(row["selected_course_ids"]))
                except HTTPException as error:
                    connection.execute("UPDATE account_learning SET desired_state='paused',state='failed',message=?,current_task_id=NULL,active_course_titles='[]' WHERE account_id=?", (str(error.detail), account_id))
                    return
                if not selected:
                    connection.execute("UPDATE account_learning SET desired_state='stopped',state='stopped',current_task_id=NULL,active_course_titles='[]' WHERE account_id=?", (account_id,))
                    return
                checkpoint = {"runtime": "original-console", "account_managed": True, "revision": row["revision"],
                              "selected_course_ids": [course["id"] for course in selected], "course_titles": sorted({course["title"] for course in selected}),
                              "options": json.loads(row["execution_rules"]) if row["execution_rules"] else self.service.study_settings(account_id)}
                task_id = self.insert_task(connection, account_id, "study", checkpoint)
            connection.execute("UPDATE account_learning SET state='queued',message='等待启动学习',current_task_id=?,active_course_titles='[]',updated_at=? WHERE account_id=?", (task_id, now, account_id))
        else:
            state = row["state"] if row["state"] in ("idle", "completed", "failed") else row["desired_state"]
            connection.execute("UPDATE account_learning SET state=?,current_task_id=NULL,active_course_titles='[]',updated_at=? WHERE account_id=?", (state, now, account_id))

    def reconcile_all(self, connection):
        for row in connection.execute("SELECT account_id FROM account_learning").fetchall():
            try:
                self.reconcile(connection, row["account_id"])
            except HTTPException as error:
                connection.execute("UPDATE account_learning SET desired_state='paused',state='failed',message=?,current_task_id=NULL,active_course_titles='[]' WHERE account_id=?", (str(error.detail), row["account_id"]))

    def claimed(self, connection, task):
        row = connection.execute("SELECT 1 FROM account_learning WHERE account_id=?", (task["account_id"],)).fetchone()
        if row:
            state = "running" if task["kind"] == "study" else "refreshing"
            connection.execute("UPDATE account_learning SET state=?,current_task_id=?,active_course_titles='[]',latest_activity=NULL WHERE account_id=?", (state, task["id"], task["account_id"]))

    def finished(self, connection, task, state, message):
        row = connection.execute("SELECT * FROM account_learning WHERE account_id=?", (task["account_id"],)).fetchone()
        if not row:
            return
        checkpoint = json.loads(task["checkpoint"])
        if task["kind"] == "study" and checkpoint.get("account_managed") and checkpoint.get("revision") == row["revision"] and row["desired_state"] == "running":
            if state == "completed":
                connection.execute("UPDATE account_learning SET desired_state='stopped',state='completed',message=? WHERE account_id=?", (message, task["account_id"]))
            elif state == "failed":
                connection.execute("UPDATE account_learning SET desired_state='paused',state='failed',message=? WHERE account_id=?", (message, task["account_id"]))
        elif task["kind"] == "study" and row["desired_state"] in ("paused", "stopped") and row["state"] != "failed":
            settled = "学习已暂停，课程选择已保留" if row["desired_state"] == "paused" else "学习已停止，课程选择已保留"
            connection.execute("UPDATE account_learning SET message=? WHERE account_id=?", (settled, task["account_id"]))
        elif task["kind"] != "study":
            connection.execute("UPDATE account_learning SET message=? WHERE account_id=?", (message, task["account_id"]))
        if checkpoint.get("account_refresh"):
            connection.execute("UPDATE account_learning SET refresh_pending=0,refresh_error=? WHERE account_id=?", (message if state == "failed" else None, task["account_id"]))
        self.reconcile(connection, task["account_id"])

    def log_activity(self, task, text):
        if task["kind"] != "study":
            return
        checkpoint = json.loads(task["checkpoint"])
        if not checkpoint.get("account_managed"):
            return
        titles = checkpoint.get("course_titles", [])
        title = next((title for title in titles if f"[{title}]" in text or f"【{title}】" in text), None)
        with self.db.connect(immediate=True) as connection:
            row = connection.execute("SELECT active_course_titles FROM account_learning WHERE account_id=? AND current_task_id=?", (task["account_id"], task["id"])).fetchone()
            if not row:
                return
            active = json.loads(row["active_course_titles"])
            if title and "正在学习该课程" in text and title not in active:
                active.append(title)
            elif title and "课程学习完毕" in text and title in active:
                active.remove(title)
            elif "所有待学习课程学习完毕" in text:
                active = []
            activity = {"message": text, "created_at": time.time(), "course_title": title}
            connection.execute("UPDATE account_learning SET active_course_titles=?,latest_activity=? WHERE account_id=?", (json.dumps(active, ensure_ascii=False), json.dumps(activity, ensure_ascii=False), task["account_id"]))

    def compatibility_start(self, account_id, course_ids, fingerprint=None, course_id=None):
        with self.db.connect(immediate=True) as connection:
            row = self.ensure(connection, account_id)
            if row["desired_state"] == "running":
                raise HTTPException(409, "账号正在学习，可在账号页调整课程选择")
            self.validate_selection(connection, account_id, course_ids)
            if not course_ids:
                raise HTTPException(409, "请先选择需要学习的课程")
            rules = self.validate_plan(account_id, fingerprint, course_id)
            connection.execute("UPDATE account_learning SET execution_rules=? WHERE account_id=?", (json.dumps(rules), account_id))
            connection.execute("UPDATE account_learning SET selected_course_ids=?,revision=revision+1,desired_state='running',state='queued',updated_at=? WHERE account_id=?", (json.dumps(course_ids), time.time(), account_id))
            self.reconcile(connection, account_id)
            if course_id is not None:
                connection.execute("UPDATE tasks SET course_id=? WHERE id=(SELECT current_task_id FROM account_learning WHERE account_id=?) AND kind='study' AND state='queued'", (course_id, account_id))
        snapshot = self.snapshot(account_id)
        task = self.db.one("SELECT * FROM tasks WHERE id=?", (snapshot["current_task_id"],))
        return task
