"""Android boundary contracts verified without contacting Chaoxing."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess

from cryptography.fernet import Fernet
import httpx
import pytest
from pydantic import ValidationError

from backend.app.config import Config
from backend.app.main import create_app
from backend.app.schemas import AccountCreate, AccountUpdate, AIPreview, Setup
from backend.app.security import Vault
from backend.app.worker import Worker


def test_console_timezone_reads_android_current_offset(monkeypatch):
    import sys
    from types import SimpleNamespace
    from backend.app.android.runtime import console_timezone
    class Zone:
        def getID(self): return "Asia/Shanghai"
        def getOffset(self, milliseconds):
            assert milliseconds == 125000
            return 28800000
    classes = {"java.util.TimeZone": SimpleNamespace(getDefault=lambda: Zone()),
               "java.lang.System": SimpleNamespace(currentTimeMillis=lambda: 125000)}
    monkeypatch.setitem(sys.modules, "java", SimpleNamespace(jclass=lambda name: classes[name]))
    assert console_timezone() == ("Asia/Shanghai", 28800)


@pytest.mark.parametrize("address,expected", [
    ("127.0.0.1", 200), ("192.168.8.20", 200), ("10.1.2.3", 200),
    ("172.16.1.9", 200), ("169.254.1.1", 200), ("::1", 200), ("fd12::1", 200),
    ("8.8.8.8", 403), ("100.64.0.1", 403), ("172.32.0.1", 403), ("invalid", 403),
])
def test_lan_listener_validates_socket_peer(tmp_path, address, expected):
    app = create_app(Config(tmp_path, Fernet.generate_key().decode(), "t" * 32, lan_only=True))

    async def request():
        transport = httpx.ASGITransport(app, client=(address, 9000))
        async with httpx.AsyncClient(transport=transport, base_url="http://device") as client:
            # Forwarded headers cannot turn a public peer into a LAN peer.
            return await client.get("/api/health", headers={"X-Forwarded-For": "192.168.8.2"})
    assert asyncio.run(request()).status_code == expected


def test_lan_http_session_cookie_and_csrf(tmp_path):
    config = Config(tmp_path, Fernet.generate_key().decode(), "t" * 32, secure_cookie=False, lan_only=True,
                    session_cookie="study_android_session")
    app = create_app(config)

    async def request():
        transport = httpx.ASGITransport(app, client=("192.168.8.20", 9000))
        async with httpx.AsyncClient(transport=transport, base_url="http://192.168.8.1:8080") as client:
            assert (await client.get("/api/accounts")).status_code == 401
            setup = await client.post("/api/auth/setup", json={"username": "admin", "password": "http-test-password-long",
                                                              "setup_token": config.setup_token})
            assert setup.status_code == 200
            header = setup.headers["set-cookie"].lower()
            assert header.startswith("study_android_session=")
            assert "secure" not in header and "httponly" in header and "samesite=strict" in header
            # The cookie jar must send the login cookie automatically over HTTP.
            assert (await client.get("/api/accounts")).status_code == 200
            account = {"label": "LAN", "username": "fixture", "password": "fixture"}
            assert (await client.post("/api/accounts", json=account)).status_code == 403
            client.headers["X-CSRF-Token"] = setup.json()["csrf"]
            assert (await client.post("/api/accounts", json=account)).status_code == 200
            assert (await client.post("/api/auth/logout")).status_code == 200
            assert (await client.get("/api/accounts")).status_code == 401

    asyncio.run(request())


def test_vault_factory_shared_by_api_and_worker(tmp_path):
    created = []

    def factory(key):
        vault = Vault(key)
        created.append(vault)
        return vault

    config = Config(tmp_path, Fernet.generate_key().decode(), "t" * 32, vault_factory=factory)
    app, worker = create_app(config), Worker(config)
    assert app.state.vault is created[0] and worker.vault is created[1]
    assert worker.vault.open(app.state.vault.seal({"account": "fixture"})) == {"account": "fixture"}


def test_secret_and_collection_limits_across_pydantic_versions():
    with pytest.raises(ValidationError):
        Setup(username="admin", password="short", setup_token="t" * 32)
    with pytest.raises(ValidationError):
        AccountCreate(label="a", username="", password="p")
    with pytest.raises(ValidationError):
        AccountUpdate(label="a", password="p" * 257)
    with pytest.raises(ValidationError):
        AIPreview(question="q", options=["x"] * 51)
    with pytest.raises(ValidationError):
        AccountCreate(label="a", username="u", password="p", extra="rejected")
    assert AccountUpdate(label="a").model_dump()["password"] is None


def test_java_and_python_fernet_interoperate(tmp_path):
    java_home = Path(os.environ.get("JAVA_HOME", "/nonexistent")) / "bin"
    javac = shutil.which("javac") or next(iter(java_home.glob("javac*")), None)
    java = shutil.which("java") or next(iter(java_home.glob("java.exe")), None) or next(iter(java_home.glob("java")), None)
    if not javac or not java:
        pytest.skip("JDK required for Java/Python Fernet interoperation")
    source = Path(__file__).resolve().parents[2] / "android/app/src/main/java/cn/zrmug/chaoxing/FernetCipher.java"
    harness = tmp_path / "Interop.java"
    harness.write_text('''import cn.zrmug.chaoxing.FernetCipher;
import java.io.*;
public class Interop {
  public static void main(String[] args) throws Exception {
    BufferedReader input = new BufferedReader(new InputStreamReader(System.in, "UTF-8"));
    FernetCipher cipher = new FernetCipher(input.readLine());
    System.out.println(cipher.decrypt(input.readLine()));
    System.out.println(cipher.encrypt(input.readLine()));
  }
}''', encoding="utf-8")
    subprocess.run([str(javac), "-encoding", "UTF-8", "-d", str(tmp_path), str(source), str(harness)], check=True, capture_output=True)
    key = Fernet.generate_key()
    value = json.dumps({"课程": "隔离账号", "cookies": []}, ensure_ascii=False)
    token = Fernet(key).encrypt(value.encode()).decode()
    result = subprocess.run([str(java), "-Dfile.encoding=UTF-8", "-cp", str(tmp_path), "Interop"],
                            input=f"{key.decode()}\n{token}\n{value}\n", capture_output=True,
                            text=True, encoding="utf-8", check=True)
    decrypted, encrypted = result.stdout.splitlines()
    assert decrypted == value
    assert Fernet(key).decrypt(encrypted.encode()).decode() == value
