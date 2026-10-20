"""Yatori-compatible custom question bank protocol."""
import hashlib
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from .adapters.contracts import AdapterError
from .ai import preview_answer, validate_endpoint


def validate_bank_endpoint(config):
    if not config.get("allow_lan"):
        return validate_endpoint(config["url"])
    parsed = urlparse(config["url"])
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("题库地址格式不正确")
    if parsed.scheme == "https":
        return
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 80, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("题库地址无法解析") from None
    networks = [ipaddress.ip_network(x) for x in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7")]
    if not addresses or any(not any(ipaddress.ip_address(item[4][0]) in network for network in networks
                                  if ipaddress.ip_address(item[4][0]).version == network.version) for item in addresses):
        raise ValueError("HTTP 题库地址须位于本机或局域网")


def lookup(config, question, options, question_type="unknown"):
    if not config.get("enabled") or not config.get("url"):
        raise AdapterError("bank_config", "请先启用并配置题库接口")
    validate_bank_endpoint(config)
    payload = {"md5": hashlib.md5((question_type + question).encode()).hexdigest(),
               "type": question_type, "content": question, "options": options, "answers": []}
    headers = {"Authorization": "Bearer " + config["token"]} if config.get("token") else {}
    try:
        with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
            response = client.post(config["url"], headers=headers, json=payload)
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError()
            data = response.json()
            if not isinstance(data, dict) or data.get("code", 0) not in (0, 1, 200):
                raise ValueError()
            candidates = (data, data.get("question"), data.get("data"))
            for candidate in candidates:
                if isinstance(candidate, dict):
                    candidate = candidate.get("answers", candidate.get("answer"))
                if isinstance(candidate, str) and candidate.strip():
                    return candidate[:32000]
                if isinstance(candidate, list) and candidate and all(isinstance(x, str) for x in candidate):
                    return "\n".join(candidate)[:32000]
    except (httpx.HTTPError, ValueError, TypeError):
        raise AdapterError("bank_error", "题库请求失败，请检查地址、授权和返回格式") from None
    raise AdapterError("bank_empty", "题库尚未返回这道题的答案")


def answer_preview(service, question, options, question_type):
    bank = service.secret_settings("question_bank", True)
    if bank["enabled"]:
        try:
            return {"answer": lookup(bank, question, options, question_type), "source": "question_bank", "requires_review": True}
        except AdapterError:
            if not bank["ai_fallback"]:
                raise
    return {"answer": preview_answer(service.ai_settings(True), question, options), "source": "ai", "requires_review": True}
