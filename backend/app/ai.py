import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from .adapters.contracts import AdapterError


def console_ai_endpoint(url: str) -> str:
    """Expand standard API base URLs for Console's complete endpoint field."""
    endpoint = url.strip()
    if not endpoint:
        return ""
    try:
        parsed = urlparse(endpoint)
    except ValueError:
        return endpoint
    path = parsed.path.rstrip("/")
    if not path or re.search(r"/v\d+$", path):
        return parsed._replace(path=path + "/chat/completions").geturl()
    if path.endswith("/chat/completions"):
        return parsed._replace(path=path).geturl()
    return endpoint


def validate_endpoint(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AI 地址应为完整 HTTPS 接口地址")
    if parsed.port not in (None, 443):
        raise ValueError("AI 接口应使用 HTTPS 标准端口")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("AI 接口域名无法解析") from None
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("AI 接口需要可公开访问的服务地址")


def preview_answer(config: dict, question: str, options: list[str], *, structured=False) -> str:
    if not config.get("enabled") or not config.get("api_key") or not config.get("model"):
        raise AdapterError("ai_config", "请先启用并配置 AI 接口")
    validate_endpoint(config["base_url"])
    try:
        with httpx.Client(timeout=45, trust_env=False, follow_redirects=False) as client:
            style = config.get("api_style", "chat")
            suffix = "/responses" if style == "responses" else "/chat/completions"
            endpoint = config["base_url"].rstrip("/")
            if not endpoint.endswith(suffix):
                endpoint += suffix
            instruction = ("只返回 JSON 字符串数组。选择题每项为选项原文，判断题返回正确或错误，填空题按空的顺序返回。"
                           "不确定则返回空数组。不要输出解释。" if structured else "请帮助理解课程问题，说明解题依据和不确定之处。")
            messages = [{"role": "system", "content": instruction},
                        {"role": "user", "content": question + "\n" + "\n".join(options)}]
            payload = {"model": config["model"], "temperature": 0.2,
                       "input" if style == "responses" else "messages": messages}
            if style == "metaso":
                payload = {"model": config["model"], "q": "\n".join(item["content"] for item in messages),
                           "format": "simple", "scope": "ducument"}
            response = client.post(endpoint, headers={"Authorization": "Bearer " + config["api_key"]},
                                   json=payload)
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            if style == "metaso":
                answer = data["answer"]
            elif style == "responses":
                answer = data.get("output_text") or "".join(
                    block["text"] for item in data["output"] for block in item.get("content", [])
                    if block.get("type") == "output_text")
            else:
                answer = data["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError()
            return answer[:32000]
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        raise AdapterError("ai_error", "AI 接口请求失败，请检查服务地址、模型与授权") from None
