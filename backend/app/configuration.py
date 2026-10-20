"""Yatori generator YAML contract, with transactional encrypted persistence."""
import json
import time
from urllib.parse import urlparse

import yaml

from .schemas import StudySettings
from .learning import rules_with_defaults
from .notifications import MAILBOX

VIDEO = ["off", "normal", "multi_course", "multi_node"]
ANSWER = ["off", "ai", "question_bank", "chaoxing_ai"]
SUBMIT = ["save", "submit", "complete"]
PROVIDERS = {
    "OPENAI": "https://api.openai.com/v1", "DEEPSEEK": "https://api.deepseek.com",
    "SILICON": "https://api.siliconflow.cn/v1", "CHATGLM": "https://open.bigmodel.cn/api/paas/v4",
    "TONGYI": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "XINGHUO": "https://spark-api-open.xf-yun.com/v1", "DOUBAO": "https://ark.cn-beijing.volces.com/api/v3",
    "METAAI": "https://metaso.cn/api/v1",
}


def rules_to_yatori(rules):
    return {"videoModel": VIDEO.index(rules["video_mode"]), "autoExam": ANSWER.index(rules["answer_mode"]),
            "examAutoSubmit": SUBMIT.index(rules["submit_mode"]), "cxNode": rules["node_concurrency"],
            "cxChapterTestSw": int(rules["chapter_test"]), "cxWorkSw": int(rules["work"]),
            "cxExamSw": int(rules["exam"]), "shuffleSw": int(rules["shuffle"]),
            "includeCourses": rules["include_courses"], "excludeCourses": rules["exclude_courses"]}


def rules_from_yatori(value):
    defaults = rules_with_defaults()
    for source, target, choices in (("videoModel", "video_mode", VIDEO), ("autoExam", "answer_mode", ANSWER),
                                    ("examAutoSubmit", "submit_mode", SUBMIT)):
        number = int(value.get(source, 1 if source == "videoModel" else 0))
        if not 0 <= number < len(choices):
            raise ValueError()
        defaults[target] = choices[number]
    for source, target, default in (("cxChapterTestSw", "chapter_test", 1), ("cxWorkSw", "work", 1),
                                     ("cxExamSw", "exam", 1), ("shuffleSw", "shuffle", 0)):
        number = int(value.get(source, default))
        if number not in (0, 1):
            raise ValueError()
        defaults[target] = bool(number)
    defaults["node_concurrency"] = int(value.get("cxNode", 3))
    for source, target in (("includeCourses", "include_courses"), ("excludeCourses", "exclude_courses")):
        entries = value.get(source) or []
        if not isinstance(entries, list) or len(entries) > 200 or any(not isinstance(x, str) or not x.strip() or len(x) > 256 for x in entries):
            raise ValueError()
        defaults[target] = list(dict.fromkeys(x.strip() for x in entries))
    return StudySettings(**defaults).model_dump()


def export_configuration(service, include_secrets=False):
    ai, bank, email = service.ai_settings(True), service.secret_settings("question_bank", True), service.secret_settings("email", True)
    users = []
    for account in service.db.rows("SELECT * FROM accounts ORDER BY id"):
        credentials = service.vault.open(account["credentials"])
        preferences = service.account_preferences(account["id"], True)
        users.append({"accountType": "XUEXITONG", "remarkName": account["label"], "account": credentials["username"],
                      "password": credentials["password"] if include_secrets else "",
                      "isProxy": int(bool(preferences["proxy_url"])),
                      "informEmails": preferences["inform_emails"], "coursesCustom": rules_to_yatori(service.study_settings(account["id"])),
                      "console": {"rules": service.study_settings(account["id"]),
                                  "proxyUrl": preferences["proxy_url"] if include_secrets else ""}})
    basic = service.db.settings()
    value = {"setting": {"basicSetting": {"logLevel": basic["log_level"].upper(), "completionTone": int(basic["completion_tone"]),
                         "colorLog": int(basic["color_log"]), "logOutFileSw": int(basic["log_out_file"])},
             "emailInform": {"sw": int(email["enabled"]), "SMTPHost": email["host"], "SMTPPort": str(email["port"]),
                             "userName": email["username"], "email": email["sender"],
                             "password": email["password"] if include_secrets else ""},
             "aiSetting": {"aiType": "METAAI" if ai["api_style"] == "metaso" else "OTHER", "aiUrl": ai["base_url"], "model": ai["model"],
                           "API_KEY": ai["api_key"] if include_secrets else ""},
             "apiQueSetting": {"url": bank["url"], "exType": "CUSTOM", "exToken": bank["token"] if include_secrets else ""}},
             "users": users,
             "console": {"ai_enabled": ai["enabled"], "ai_style": ai["api_style"], "bank_enabled": bank["enabled"],
                         "ai_fallback": bank["ai_fallback"], "email_recipients": email["recipients"],
                         "bank_allow_lan": bank["allow_lan"],
                         "email_security": email["security"], "contains_secrets": include_secrets}}
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)


def import_configuration(service, text):
    try:
        if len(text) > 100000 or any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in yaml.scan(text)):
            raise ValueError()
        value = yaml.safe_load(text)
        if not isinstance(value, dict) or not isinstance(value.get("users"), list) or len(value["users"]) > 200:
            raise ValueError()
        return _apply(service, value)
    except yaml.YAMLError:
        raise ValueError() from None


def _apply(service, value):
    users, existing, seen = [], {}, set()
    for account in service.db.rows("SELECT * FROM accounts"):
        credential = service.vault.open(account["credentials"])
        if credential["username"] in existing:
            raise ValueError()
        existing[credential["username"]] = account
    for user in value["users"]:
        if user.get("accountType", "").upper() != "XUEXITONG":
            raise ValueError()
        username = user["account"].strip()
        password = user.get("password") or ""
        old = existing.get(username)
        label = user.get("remarkName") or (old["label"] if old else "学习通账号")
        if not username or len(username) > 128 or not isinstance(password, str) or len(password) > 256 or not 1 <= len(label) <= 80 or username in seen:
            raise ValueError()
        if not password:
            if old is None:
                raise ValueError()
            password = service.vault.open(old["credentials"])["password"]
        seen.add(username)
        rules = rules_from_yatori(user.get("coursesCustom") or {})
        extension = user.get("console") or {}
        if extension.get("rules"):
            rules = StudySettings(**(rules | extension["rules"])).model_dump()
        preferences = service.account_preferences(old["id"], True) if old else {"proxy_url": "", "inform_emails": []}
        emails = user.get("informEmails") or []
        if not isinstance(emails, list) or len(emails) > 20 or any(not isinstance(x, str) or not MAILBOX.fullmatch(x) for x in emails):
            raise ValueError()
        preferences["inform_emails"] = emails
        proxy = extension.get("proxyUrl") or preferences["proxy_url"]
        if int(user.get("isProxy", 0)):
            parsed = urlparse(proxy)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.port or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                raise ValueError()
            preferences["proxy_url"] = proxy
        else:
            preferences["proxy_url"] = ""
        users.append((old, label, {"username": username, "password": password}, rules, preferences))
    settings, extension = value.get("setting") or {}, value.get("console") or {}
    updates = {}
    if "aiSetting" in settings:
        a = settings["aiSetting"]
        ai = service.ai_settings(True)
        kind = a.get("aiType", "OTHER").upper()
        endpoint = a.get("aiUrl") or PROVIDERS.get(kind)
        if not endpoint:
            raise ValueError()
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
        ai.update(base_url=endpoint, model=str(a.get("model") or ""), api_key=a.get("API_KEY") or ai["api_key"],
                  enabled=bool(extension.get("ai_enabled", bool(a.get("API_KEY") and a.get("model")))),
                  api_style=extension.get("ai_style", "metaso" if kind == "METAAI" else "chat"))
        if ai["api_style"] not in ("chat", "responses", "metaso"):
            raise ValueError()
        updates["ai"] = service.vault.seal(ai)
    if "apiQueSetting" in settings:
        a = settings["apiQueSetting"]
        if a.get("exType", "CUSTOM").upper() not in ("CUSTOM", ""):
            raise ValueError()
        bank = service.secret_settings("question_bank", True)
        endpoint = a.get("url") or ""
        if endpoint:
            parsed = urlparse(endpoint)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError()
        bank.update(url=endpoint, token=a.get("exToken") or bank["token"],
                    enabled=bool(extension.get("bank_enabled", bool(endpoint))), ai_fallback=bool(extension.get("ai_fallback", False)),
                    allow_lan=bool(extension.get("bank_allow_lan", endpoint.startswith("http://"))))
        updates["question_bank"] = service.vault.seal(bank)
    if "emailInform" in settings:
        a = settings["emailInform"]
        email = service.secret_settings("email", True)
        email.update(enabled=bool(a.get("sw")), host=a.get("SMTPHost") or a.get("smtpHost") or "",
                     port=int(a.get("SMTPPort") or a.get("smtpPort") or 465),
                     username=a.get("userName") or a.get("email") or "", sender=a.get("email") or a.get("userName") or "",
                     password=a.get("password") or email["password"], recipients=extension.get("email_recipients", email["recipients"]),
                     security=extension.get("email_security", "ssl"))
        if not 1 <= email["port"] <= 65535 or email["security"] not in ("ssl", "starttls"):
            raise ValueError()
        updates["email"] = service.vault.seal(email)
    log_level = str((settings.get("basicSetting") or {}).get("logLevel", "INFO")).lower()
    if log_level == "warn":
        log_level = "warning"
    if log_level not in ("debug", "info", "warning", "error"):
        raise ValueError()
    updates["log_level"] = log_level
    for key, target, default in (("completionTone", "completion_tone", False), ("colorLog", "color_log", True), ("logOutFileSw", "log_out_file", False)):
        entry = int((settings.get("basicSetting") or {}).get(key, int(default)))
        if entry not in (0, 1):
            raise ValueError()
        updates[target] = bool(entry)
    with service.db.connect(immediate=True) as connection:
        for old, label, credential, rules, preferences in users:
            if old:
                account_id = old["id"]
                connection.execute("UPDATE accounts SET label=?,credentials=?,cookies=NULL,status='new' WHERE id=?",
                                   (label, service.vault.seal(credential), account_id))
            else:
                account_id = connection.execute("INSERT INTO accounts(label,credentials,created_at) VALUES(?,?,?)",
                                                (label, service.vault.seal(credential), time.time())).lastrowid
            connection.execute("INSERT OR REPLACE INTO learning_rules VALUES(?,?)", (account_id, json.dumps(rules)))
            connection.execute("INSERT OR REPLACE INTO account_preferences VALUES(?,?)", (account_id, service.vault.seal(preferences)))
        for key, data in updates.items():
            connection.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(data)))
    return {"accounts": len(users), "message": "配置已导入，请验证账号后同步课程"}
