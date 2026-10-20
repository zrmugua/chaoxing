"""Encrypted SMTP settings and task result notifications."""
from email.message import EmailMessage
import ipaddress
import re
import smtplib
import socket
import ssl

from .adapters.contracts import AdapterError


MAILBOX = re.compile(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+")


def validate_email(config, resolve=True):
    if not config["enabled"]:
        return
    if not config["host"] or re.search(r"[\s/:@]", config["host"]):
        raise ValueError("请填写 SMTP 服务器域名")
    addresses = [config["sender"], *config["recipients"]]
    if not config["recipients"] or len(config["recipients"]) > 20 or any(not MAILBOX.fullmatch(x) for x in addresses):
        raise ValueError("请填写有效的发件邮箱和收件邮箱，收件人最多 20 个")
    if "\n" in config["username"] or "\r" in config["username"]:
        raise ValueError("SMTP 用户名格式不正确")
    if resolve:
        try:
            results = socket.getaddrinfo(config["host"], config["port"], type=socket.SOCK_STREAM)
        except OSError:
            raise ValueError("SMTP 服务器无法解析") from None
        if not results or any(not ipaddress.ip_address(item[4][0]).is_global for item in results):
            raise ValueError("请使用可公开访问的 SMTP 服务")


def send_email(config, subject, text):
    if not config["enabled"]:
        return
    validate_email(config)
    mail = EmailMessage()
    mail["Subject"], mail["From"] = subject, config["sender"]
    mail["To"] = ", ".join(config["recipients"])
    mail.set_content(text)
    try:
        context = ssl.create_default_context()
        if config["security"] == "ssl":
            client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=20, context=context)
        else:
            client = smtplib.SMTP(config["host"], config["port"], timeout=20)
        with client:
            if config["security"] == "starttls":
                client.starttls(context=context)
            if config["username"]:
                client.login(config["username"], config["password"])
            client.send_message(mail)
    except (OSError, smtplib.SMTPException):
        raise AdapterError("email_error", "邮件发送失败，请检查 SMTP 地址、授权和收件人") from None


def notify_task(service, task, state, message):
    if task["kind"] != "study":
        return
    event = {"succeeded": "on_success", "failed": "on_failure", "waiting_manual": "on_attention",
             "awaiting_confirmation": "on_attention"}.get(state)
    config = service.secret_settings("email", True)
    recipients = service.account_preferences(task["account_id"], True)["inform_emails"] if task.get("account_id") else []
    if recipients:
        config["recipients"] = recipients
    if event and config["enabled"] and config[event]:
        send_email(config, "学习通管理台 · 任务状态更新",
                   f"任务 #{task['id']}\n状态：{state}\n{message}\n请打开管理台查看详情。")
