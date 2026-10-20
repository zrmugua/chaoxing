"""Learning rules and service configuration routes."""
import json
from urllib.parse import urlparse

from fastapi import Depends, HTTPException

from .ai import validate_endpoint
from .notifications import send_email, validate_email, MAILBOX
from .question_bank import answer_preview
from .question_bank import validate_bank_endpoint
from .schemas import StudySettings, QuestionBankSettings, EmailSettings, AIPreview, AccountPreferences, ConfigImport, PlanStart
from .configuration import export_configuration, import_configuration


def install_settings_routes(app, db, vault, service, authenticated):
    auth = [Depends(authenticated)]

    def normalize_rules(body):
        value = body.model_dump()
        for key in ("include_courses", "exclude_courses"):
            entries = value[key]
            if len(entries) > 200 or any(not x.strip() or len(x) > 256 for x in entries):
                raise HTTPException(422, "课程筛选最多 200 项，每项填写课程名称或编号")
            value[key] = list(dict.fromkeys(x.strip() for x in entries))
        return value

    @app.get("/api/settings/study", dependencies=auth)
    def study_settings():
        return service.study_settings()

    @app.put("/api/settings/study", dependencies=auth)
    def save_study(body: StudySettings):
        db.set_setting("study", normalize_rules(body))
        return service.study_settings()

    @app.get("/api/accounts/{account_id}/study-settings", dependencies=auth)
    def account_study(account_id: int):
        return {"rules": service.study_settings(account_id),
                "overridden": bool(db.one("SELECT 1 FROM learning_rules WHERE account_id=?", (account_id,)))}

    @app.put("/api/accounts/{account_id}/study-settings", dependencies=auth)
    def save_account_study(account_id: int, body: StudySettings):
        service.account(account_id)
        db.execute("INSERT INTO learning_rules VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET payload=excluded.payload",
                   (account_id, json.dumps(normalize_rules(body))))
        return account_study(account_id)

    @app.delete("/api/accounts/{account_id}/study-settings", dependencies=auth)
    def reset_account_study(account_id: int):
        service.account(account_id)
        db.execute("DELETE FROM learning_rules WHERE account_id=?", (account_id,))
        return account_study(account_id)

    @app.post("/api/accounts/{account_id}/study", dependencies=auth)
    def study_account(account_id: int, body: PlanStart | None = None):
        plan = service.study_plan(account_id)
        if body is not None and body.fingerprint != plan["fingerprint"]:
            raise HTTPException(409, "学习规则或课程已更新，请重新查看启动摘要")
        result = service.queue_courses(account_id, plan)
        result["tasks"] = [{k: v for k, v in task.items() if k != "checkpoint"} for task in result["tasks"]]
        return result

    @app.get("/api/accounts/{account_id}/study-plan", dependencies=auth)
    def study_plan(account_id: int, course_id: int | None = None):
        return service.study_plan(account_id, course_id)

    @app.get("/api/accounts/{account_id}/preferences", dependencies=auth)
    def account_preferences(account_id: int):
        return service.account_preferences(account_id)

    @app.put("/api/accounts/{account_id}/preferences", dependencies=auth)
    def save_preferences(account_id: int, body: AccountPreferences):
        value = service.account_preferences(account_id, True)
        if len(body.inform_emails) > 20 or any(not MAILBOX.fullmatch(x) for x in body.inform_emails):
            raise HTTPException(422, "请填写有效的通知邮箱，最多 20 个")
        value["inform_emails"] = list(dict.fromkeys(body.inform_emails))
        if body.proxy_url is not None:
            proxy = body.proxy_url.get_secret_value().strip()
            try:
                parsed = urlparse(proxy)
                if proxy and (parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.port or
                              parsed.path not in ("", "/") or parsed.query or parsed.fragment):
                    raise ValueError()
            except ValueError:
                raise HTTPException(422, "代理地址格式为 http://主机:端口 或 https://主机:端口") from None
            value["proxy_url"] = proxy
        db.execute("INSERT INTO account_preferences VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET payload=excluded.payload",
                   (account_id, vault.seal(value)))
        return account_preferences(account_id)

    @app.get("/api/configuration/export", dependencies=auth)
    def export_config(include_secrets: bool = False):
        from fastapi.responses import Response
        return Response(export_configuration(service, include_secrets), media_type="application/yaml",
                        headers={"Content-Disposition": 'attachment; filename="yatori-config.yml"'})

    @app.post("/api/configuration/import", dependencies=auth)
    def import_config(body: ConfigImport):
        if db.one("SELECT id FROM tasks WHERE state IN ('running','pausing','stopping') LIMIT 1"):
            raise HTTPException(409, "请先暂停正在运行的任务，再导入配置")
        try:
            return import_configuration(service, body.text.get_secret_value())
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise HTTPException(422, "配置无法导入，请检查学习通账号、规则和服务配置；已有账号可保留空密码") from None

    @app.get("/api/courses/{course_id}/assessments", dependencies=auth)
    def assessments(course_id: int):
        service.course(course_id)
        return db.rows("SELECT * FROM assessments WHERE course_id=? ORDER BY kind,id",(course_id,))

    @app.post("/api/courses/{course_id}/assessments/sync", dependencies=auth)
    def sync_assessments(course_id: int):
        task=service.queue(service.course(course_id)["account_id"],"sync_assessments",course_id)
        return {key:value for key,value in task.items() if key!="checkpoint"}

    @app.get("/api/settings/question-bank", dependencies=auth)
    def bank_settings():
        return service.secret_settings("question_bank")

    @app.put("/api/settings/question-bank", dependencies=auth)
    def save_bank(body: QuestionBankSettings):
        value = body.model_dump(exclude={"token"})
        if body.enabled:
            try:
                if body.allow_lan:
                    validate_bank_endpoint(value)
                else:
                    validate_endpoint(body.url)
            except ValueError:
                raise HTTPException(422, "请检查题库地址；HTTP 本机或局域网题库需开启局域网接口选项") from None
        value["token"] = body.token.get_secret_value() if body.token is not None else service.secret_settings("question_bank", True)["token"]
        db.set_setting("question_bank", vault.seal(value))
        return bank_settings()

    @app.post("/api/answers/preview", dependencies=auth)
    def preview(body: AIPreview):
        try:
            return answer_preview(service, body.question, body.options, body.question_type)
        except ValueError:
            raise HTTPException(422, "答案服务地址无法使用，请检查配置") from None

    @app.get("/api/settings/email", dependencies=auth)
    def email_settings():
        return service.secret_settings("email")

    @app.put("/api/settings/email", dependencies=auth)
    def save_email(body: EmailSettings):
        value = body.model_dump(exclude={"password"})
        try:
            validate_email(value)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        value["password"] = body.password.get_secret_value() if body.password is not None else service.secret_settings("email", True)["password"]
        db.set_setting("email", vault.seal(value))
        return email_settings()

    @app.post("/api/settings/email/test", dependencies=auth)
    def test_email():
        config = service.secret_settings("email", True)
        if not config["enabled"]:
            raise HTTPException(409, "请先启用并保存邮件配置")
        try:
            send_email(config, "学习通管理台 · 邮件测试", "邮件通知连接成功。")
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}
