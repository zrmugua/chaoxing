import base64
import hashlib
import hmac
import json
import re
import secrets

class Vault:
    def __init__(self, key: str):
        from cryptography.fernet import Fernet
        self.cipher = Fernet(key.encode())

    def seal(self, value) -> str:
        return self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()

    def open(self, value: str):
        return json.loads(self.cipher.decrypt(value.encode()))


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + derived).decode()


def password_matches(password: str, encoded: str) -> bool:
    raw = base64.b64decode(encoded)
    return hmac.compare_digest(password_hash(password, raw[:16]), encoded)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def redact(text: str, secrets_to_hide=(), limit=1000) -> str:
    for value in sorted((str(s) for s in secrets_to_hide if s), key=len, reverse=True):
        text = text.replace(value, "[已过滤]")
    text = re.sub(r"(?im)(authorization|cookie|set-cookie)[\"']?\s*[:=][^\r\n]*", r"\1: [已过滤]", text)
    text = re.sub(r"(?i)(password|api[_-]?key|token|dtoken|jtoken|uname|_uid|enc)\s*[\"']?\s*[:=]\s*[\"']?[^\s,;&\"'}]+", r"\1=[已过滤]", text)
    text = re.sub(r"(?i)(?<![a-z0-9])(enc_)[^&\s\"'<>]+", r"\1[已过滤]", text)
    text = re.sub(r"(?i)(/multimedia/log/a/[^/?\s\"']+/)[^/?\s\"']+", r"\1[已过滤]", text)
    text = re.sub(r"\b1[3-9]\d{9}\b", "[手机号]", text)
    return text[:limit]
