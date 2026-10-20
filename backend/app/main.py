import hmac
import ipaddress
import json
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai import preview_answer, validate_endpoint
from .config import Config
from .db import Database
from .schemas import AccountCreate, AccountUpdate, AISettings, AIPreview, Login, SettingsUpdate, Setup, TaskAction, PlanStart
from .security import Vault, digest, password_hash, password_matches
from .services import ACTIVE, PlatformService
from .adapters.contracts import AdapterError
from .settings_routes import install_settings_routes


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    db = Database(config.data_dir / "console.sqlite3")
    vault = (config.vault_factory or Vault)(config.master_key)
    marker = db.one("SELECT value FROM settings WHERE key='vault_check'")
    if marker:
        vault.open(json.loads(marker["value"]))
    else:
        db.set_setting("vault_check", vault.seal("study-console"))
    service = PlatformService(db, vault)
    app = FastAPI(title="学习通管理平台", version="0.5.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.vault = db, vault

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        return JSONResponse({"detail": "输入格式不符合要求，请检查必填字段和长度"}, status_code=422)

    @app.exception_handler(AdapterError)
    async def adapter_error(request, error):
        return JSONResponse({"detail": str(error), "code": error.code}, status_code=409)

    @app.exception_handler(Exception)
    async def internal_error(request, error):
        db.log("管理请求处理异常，请检查服务状态", level="error")
        return JSONResponse({"detail": "服务处理失败，请查看系统日志并重试"}, status_code=500)

    @app.middleware("http")
    async def security_headers(request, call_next):
        if config.lan_only:
            try:
                peer = ipaddress.ip_address(request.client.host)
                allowed = (peer.is_loopback or any(peer in net for net in LAN_NETWORKS if peer.version == net.version))
            except (ValueError, AttributeError):
                allowed = False
            if not allowed:
                return JSONResponse({"detail": "仅允许局域网访问"}, status_code=403)
        try:
            content_length = int(request.headers.get("content-length", "0") or "0")
        except ValueError:
            return JSONResponse({"detail": "请求长度格式错误"}, status_code=400)
        if content_length > 128 * 1024:
            return JSONResponse({"detail": "请求内容过大"}, status_code=413)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "请求来源校验失败"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def session(request: Request):
        token = request.cookies.get(config.session_cookie, "")
        return db.one("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?", (digest(token), time.time())) if token else None

    def authenticated(request: Request):
        row = session(request)
        if not row:
            raise HTTPException(401, "请先登录管理后台")
        if request.method not in ("GET", "HEAD") and not hmac.compare_digest(row["csrf"], request.headers.get("X-CSRF-Token", "")):
            raise HTTPException(403, "操作校验已失效，请刷新页面")
        return row

    def rate_limit(request):
        client = digest(request.client.host if request.client else "unknown")
        now = time.time()
        with db.connect(immediate=True) as c:
            row = c.execute("SELECT * FROM login_attempts WHERE client=?", (client,)).fetchone()
            if row and row["reset_at"] > now and row["count"] >= 10:
                raise HTTPException(429, "登录尝试次数较多，请在 15 分钟后重试")
            count = row["count"] + 1 if row and row["reset_at"] > now else 1
            reset = row["reset_at"] if row and row["reset_at"] > now else now + 900
            c.execute("INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)", (client, count, reset))

    def issue_session(response, username):
        token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        db.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token), csrf, time.time() + 12 * 3600))
        response.set_cookie(config.session_cookie, token, httponly=True, secure=config.secure_cookie,
                            samesite="strict", max_age=12 * 3600, path="/")
        return {"initialized": True, "authenticated": True, "csrf": csrf, "username": username}

    @app.get("/api/health")
    def health():
        db.one("SELECT version FROM schema_migrations LIMIT 1")
        return {"status": "ok"}

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        admin, current = db.one("SELECT username FROM admins WHERE id=1"), session(request)
        return {"initialized": bool(admin), "authenticated": bool(current),
                "csrf": current["csrf"] if current else "", "username": admin["username"] if admin and current else ""}

    @app.post("/api/auth/setup")
    def setup(body: Setup, request: Request, response: Response):
        rate_limit(request)
        if not hmac.compare_digest(body.setup_token.get_secret_value().encode(), config.setup_token.encode()):
            raise HTTPException(401, "初始化口令不正确")
        try:
            db.execute("INSERT INTO admins VALUES(1,?,?)", (body.username, password_hash(body.password.get_secret_value())))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "管理员已初始化，请登录") from None
        db.log("管理员初始化完成")
        return issue_session(response, body.username)

    @app.post("/api/auth/login")
    def login(body: Login, request: Request, response: Response):
        rate_limit(request)
        admin = db.one("SELECT * FROM admins WHERE id=1")
        candidate = admin["password_hash"] if admin else password_hash("unconfigured-admin")
        valid = password_matches(body.password.get_secret_value(), candidate)
        if not admin or not hmac.compare_digest(body.username.encode(), admin["username"].encode()) or not valid:
            raise HTTPException(401, "管理员账号或密码不正确")
        return issue_session(response, body.username)

    @app.post("/api/auth/logout")
    def logout(response: Response, current=Depends(authenticated)):
        db.execute("DELETE FROM sessions WHERE token_hash=?", (current["token_hash"],))
        response.delete_cookie(config.session_cookie, path="/")
        return {"ok": True}

    @app.get("/api/dashboard", dependencies=[Depends(authenticated)])
    def dashboard():
        beat = db.one("SELECT heartbeat FROM runtime WHERE id=1")
        return {"accounts": db.one("SELECT COUNT(*) AS n FROM accounts")["n"],
                "courses": db.one("SELECT COUNT(*) AS n FROM courses")["n"],
                "tasks": db.one("SELECT COUNT(*) AS n FROM tasks")["n"],
                "states": {r["state"]: r["n"] for r in db.rows("SELECT state,COUNT(*) AS n FROM tasks GROUP BY state")},
                "worker_online": bool(beat and time.time() - beat["heartbeat"] < 20),
                "heartbeat": beat["heartbeat"] if beat else None}

    @app.get("/api/accounts", dependencies=[Depends(authenticated)])
    def accounts():
        return db.rows("SELECT id,label,status,checked_at,created_at FROM accounts ORDER BY id DESC")

    @app.post("/api/accounts", dependencies=[Depends(authenticated)])
    def add_account(body: AccountCreate):
        account_id = db.execute("INSERT INTO accounts(label,credentials,created_at) VALUES(?,?,?)",
                                (body.label, vault.seal({"username": body.username.get_secret_value(),
                                                        "password": body.password.get_secret_value()}), time.time()))
        db.log(f"账号 #{account_id} 已添加")
        return {"id": account_id, "label": body.label, "status": "new"}

    @app.patch("/api/accounts/{account_id}", dependencies=[Depends(authenticated)])
    def edit_account(account_id: int, body: AccountUpdate):
        with db.connect(immediate=True) as c:
            account = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not account:
                raise HTTPException(404, "账号不存在")
            if c.execute("SELECT 1 FROM tasks WHERE account_id=? AND state IN ('running','pausing','stopping')", (account_id,)).fetchone():
                raise HTTPException(409, "请先暂停该账号正在执行的任务")
            credentials = vault.open(account["credentials"])
            if body.password:
                credentials["password"] = body.password.get_secret_value()
            c.execute("UPDATE accounts SET label=?,credentials=?,cookies=CASE WHEN ? THEN NULL ELSE cookies END,status=CASE WHEN ? THEN 'new' ELSE status END WHERE id=?",
                      (body.label, vault.seal(credentials), bool(body.password), bool(body.password), account_id))
        return {"ok": True}

    @app.delete("/api/accounts/{account_id}", dependencies=[Depends(authenticated)])
    def delete_account(account_id: int):
        with db.connect(immediate=True) as c:
            if not c.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
                raise HTTPException(404, "账号不存在")
            if c.execute("SELECT 1 FROM tasks WHERE account_id=? AND state IN ('queued','running','pausing','stopping','recovering')", (account_id,)).fetchone():
                raise HTTPException(409, "请先停止该账号的活动任务")
            c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        return {"ok": True}

    @app.post("/api/accounts/{account_id}/login", dependencies=[Depends(authenticated)])
    def account_login(account_id: int):
        return public_task(service.queue(account_id, "login"))

    @app.post("/api/accounts/{account_id}/sync", dependencies=[Depends(authenticated)])
    def account_sync(account_id: int):
        return public_task(service.queue(account_id, "sync_courses"))

    @app.get("/api/courses", dependencies=[Depends(authenticated)])
    def courses(account_id: int | None = None):
        sql = "SELECT id,account_id,remote_id,clazz_id,title,teacher,synced_at FROM courses"
        return db.rows(sql + (" WHERE account_id=?" if account_id else "") + " ORDER BY id DESC", (account_id,) if account_id else ())

    @app.get("/api/courses/{course_id}/chapters", dependencies=[Depends(authenticated)])
    def chapters(course_id: int):
        service.course(course_id)
        return db.rows("SELECT * FROM chapters WHERE course_id=? ORDER BY id", (course_id,))

    @app.post("/api/courses/{course_id}/sync", dependencies=[Depends(authenticated)])
    def chapter_sync(course_id: int):
        return public_task(service.queue(service.course(course_id)["account_id"], "sync_chapters", course_id))

    @app.post("/api/courses/{course_id}/study", dependencies=[Depends(authenticated)])
    def study(course_id: int, body: PlanStart | None = None):
        account_id = service.course(course_id)["account_id"]
        plan = service.study_plan(account_id, course_id)
        if body is not None and body.fingerprint != plan["fingerprint"]:
            raise HTTPException(409, "学习规则已更新，请重新查看启动摘要")
        return public_task(service.queue(account_id, "study", course_id, options=plan["rules"]))

    @app.get("/api/courses/{course_id}/questions", dependencies=[Depends(authenticated)])
    def questions(course_id: int):
        service.course(course_id)
        rows = db.rows("SELECT * FROM question_sets WHERE course_id=? ORDER BY id", (course_id,))
        return [{"chapter_id": row["chapter_id"], "job_id": row["job_id"], "updated_at": row["updated_at"],
                 "questions": vault.open(row["payload"])} for row in rows]

    @app.get("/api/tasks", dependencies=[Depends(authenticated)])
    def tasks(limit: int = Query(default=200, ge=1, le=1000)):
        return [public_task(r) for r in db.rows("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))]

    @app.post("/api/tasks/{task_id}/action", dependencies=[Depends(authenticated)])
    def task_action(task_id: int, body: TaskAction):
        return public_task(service.action(task_id, body.action))

    @app.get("/api/runs", dependencies=[Depends(authenticated)])
    def runs(limit: int = Query(default=200, ge=1, le=1000)):
        return db.rows("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))

    @app.get("/api/logs", dependencies=[Depends(authenticated)])
    def logs(after: int = Query(default=0, ge=0), task_id: int | None = None):
        sql, args = "SELECT * FROM logs WHERE id>?", [after]
        if task_id is not None:
            sql += " AND task_id=?"
            args.append(task_id)
        # Initial visit returns the latest window; subsequent polling advances the cursor.
        if after == 0:
            return list(reversed(db.rows(sql + " ORDER BY id DESC LIMIT 300", args)))
        return db.rows(sql + " ORDER BY id LIMIT 300", args)

    @app.get("/api/settings", dependencies=[Depends(authenticated)])
    def get_settings():
        settings = db.settings()
        settings.pop("vault_check", None)
        return settings | {"ai": service.ai_settings()}

    @app.put("/api/settings", dependencies=[Depends(authenticated)])
    def settings(body: SettingsUpdate):
        for key, value in body.model_dump().items():
            db.set_setting(key, value)
        return get_settings()

    @app.put("/api/settings/ai", dependencies=[Depends(authenticated)])
    def ai_settings(body: AISettings):
        value = body.model_dump(exclude={"api_key"})
        if body.enabled:
            try:
                validate_endpoint(body.base_url)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
        value["api_key"] = body.api_key.get_secret_value() if body.api_key is not None else service.ai_settings(True).get("api_key", "")
        db.set_setting("ai", vault.seal(value))
        return service.ai_settings()

    @app.post("/api/ai/preview", dependencies=[Depends(authenticated)])
    def ai_preview(body: AIPreview):
        try:
            answer = preview_answer(service.ai_settings(True), body.question, body.options)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return {"answer": answer, "requires_review": True}

    install_settings_routes(app, db, vault, service, authenticated)

    if config.web_dir.is_dir():
        assets = config.web_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api/") or path == "api":
                raise HTTPException(404, "接口不存在")
            return FileResponse(config.web_dir / "index.html")
    return app


def public_task(task):
    return {key: value for key, value in task.items() if key != "checkpoint"}


LAN_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                     ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fc00::/7", "fe80::/10"))
