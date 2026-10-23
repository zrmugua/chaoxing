"""Launch the original Console in a private, single-account working directory."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
import queue
import re
import signal
import subprocess
import threading
import time
from urllib.parse import urlparse

import yaml

from .ai import console_ai_endpoint
from .configuration import rules_to_yatori
from .security import redact


class ConsoleError(Exception):
    pass


def console_config(service, account, rules, titles=None):
    credentials = service.vault.open(account["credentials"])
    preferences = service.account_preferences(account["id"], True)
    ai = service.ai_settings(True)
    bank = service.secret_settings("question_bank", True)
    email = service.secret_settings("email", True)
    custom = rules_to_yatori(rules)
    if titles is not None:
        if not titles:
            raise ConsoleError("请同步并选择课程后启动")
        custom.update(includeCourses=list(dict.fromkeys(titles)), excludeCourses=[])
    basic = service.db.settings()
    value = {"setting": {
        "basicSetting": {"webModel": 0, "logModel": 0, "logLevel": "DEBUG" if basic["log_level"] == "debug" else "INFO",
                         "completionTone": 0, "colorLog": int(basic["color_log"]), "logOutFileSw": 0},
        "aiSetting": {"aiType": "METAAI" if ai["api_style"] == "metaso" else "OTHER",
                      "aiUrl": console_ai_endpoint(ai["base_url"]), "model": ai["model"], "API_KEY": ai["api_key"] if ai["enabled"] else ""},
        "apiQueSetting": {"url": bank["url"] if bank["enabled"] else ""},
        "emailInform": {"sw": int(email["enabled"]), "SMTPHost": email["host"], "SMTPPort": email["port"],
                        "userName": email["username"], "password": email["password"]}},
        "users": [{"accountType": "XUEXITONG", "remarkName": account["label"],
                   "account": credentials["username"], "password": credentials["password"],
                   "isProxy": int(bool(preferences["proxy_url"])),
                   "informEmails": preferences["inform_emails"] or email["recipients"], "coursesCustom": custom}]}
    parsed_proxy = urlparse(preferences["proxy_url"])
    secrets = [credentials["username"], credentials["password"], ai["api_key"], bank["token"], email["password"],
               preferences["proxy_url"], parsed_proxy.password, parsed_proxy.netloc if parsed_proxy.password else ""]
    return value, preferences["proxy_url"], secrets


class ConsoleProcess:
    def __init__(self, config, command=None):
        self.config = config
        self.command = command or [str(Path(config.console_binary).resolve())]

    def run(self, account_id, value, proxy, secrets, control, log, mode=None, course=None):
        folder = (self.config.data_dir / "console" / str(account_id)).resolve()
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.ownership(folder, control) as ownership_fd:
            return self._run(account_id, value, proxy, secrets, control, log, mode, course, ownership_fd)

    @staticmethod
    @contextmanager
    def ownership(folder, control):
        if os.name == "nt":
            yield None
            return
        import fcntl
        descriptor = os.open(folder / ".process.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            while True:
                control()
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(0.1)
            yield descriptor
        finally:
            # The native child shares this open file description until it exits.
            os.close(descriptor)

    def _run(self, account_id, value, proxy, secrets, control, log, mode, course, ownership_fd):
        folder = (self.config.data_dir / "console" / str(account_id)).resolve()
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache = folder / "cache"
        cache.mkdir(exist_ok=True, mode=0o700)
        private_files = ("config.yaml", "query.json", "query-result.json", "ip.txt")
        for name in private_files:
            (folder / name).unlink(missing_ok=True)
        env = dict(os.environ)
        env.pop("YATORI_BRIDGE_MODE", None)
        env.update(XDG_CACHE_HOME=str(cache), LOCALAPPDATA=str(cache), YATORI_MANAGED="1")
        if self.config.onnx_library:
            env["YATORI_ONNX_LIBRARY"] = str(Path(self.config.onnx_library).resolve())
        if self.config.model_dir:
            env["YATORI_MODEL_DIR"] = str(Path(self.config.model_dir).resolve())
        if mode:
            env["YATORI_BRIDGE_MODE"] = mode
        child = None
        reader = None
        output = queue.Queue(maxsize=2048)
        reader_stop = threading.Event()

        def private_write(name, text):
            with os.fdopen(os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as file:
                file.write(text)

        def read_output():
            try:
                while not reader_stop.is_set():
                    line = child.stdout.readline(65536)
                    if not line:
                        break
                    while not reader_stop.is_set():
                        try:
                            output.put(line, timeout=0.1)
                            break
                        except queue.Full:
                            pass
            finally:
                child.stdout.close()

        def emit(line):
            line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line).rstrip("\r\n")
            if line:
                native_level = "debug" if value.get("setting", {}).get("basicSetting", {}).get("logLevel") == "DEBUG" else "info"
                level = "error" if "[ERROR]" in line else "warning" if "[WARN]" in line else "debug" if "[DEBUG]" in line else native_level
                log(redact(line, secrets, limit=66000), level)

        try:
            control()
            private_write("config.yaml", yaml.safe_dump(value, allow_unicode=True, sort_keys=False))
            if proxy:
                parsed = urlparse(proxy)
                if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
                    raise ConsoleError("原版 Console 的代理池需要 http://主机:端口")
                private_write("ip.txt", parsed.netloc + "\n")
            if course is not None:
                original = course.get("original")
                if not original:
                    raise ConsoleError("请先同步课程，再查询章节或试卷")
                private_write("query.json", json.dumps({"course": original}, ensure_ascii=False))
            child = subprocess.Popen(self.command, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1,
                                     start_new_session=os.name != "nt",
                                     **({"pass_fds": (ownership_fd,)} if ownership_fd is not None else {}))
            reader = threading.Thread(target=read_output, daemon=True, name="console-output")
            reader.start()
            deadline = time.monotonic() + 300 if mode else None
            while child.poll() is None or reader.is_alive() or not output.empty():
                control()
                if deadline and time.monotonic() > deadline:
                    raise ConsoleError("Console 查询超时，请查看原始日志后重试")
                try:
                    emit(output.get(timeout=0.1))
                except queue.Empty:
                    pass
            code = child.wait()
            if mode:
                path = folder / "query-result.json"
                if not path.is_file() or path.stat().st_size > 10_000_000:
                    raise ConsoleError("Console 查询未返回有效结果，请查看原始日志")
                result = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ConsoleError("Console 查询未返回有效结果，请查看原始日志")
                if not result["ok"]:
                    detail = result.get("error")
                    raise ConsoleError(redact(detail, secrets) if isinstance(detail, str) and detail.strip() else "Console 查询失败，请查看原始日志")
                if code:
                    raise ConsoleError(f"Console 进程退出，退出码 {code}；请查看原始日志")
                if "data" not in result:
                    raise ConsoleError("Console 查询未返回有效结果，请查看原始日志")
                return result["data"]
            if code:
                raise ConsoleError(f"Console 进程退出，退出码 {code}；请查看原始日志")
            return None
        except (OSError, ValueError) as error:
            raise ConsoleError("Console 启动或结果读取失败，请检查安装和设备存储空间") from error
        finally:
            if child and child.poll() is None:
                if os.name != "nt":
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        os.killpg(child.pid, signal.SIGKILL)
                    else:
                        child.kill()
                    child.wait(timeout=2)
            reader_stop.set()
            if reader:
                reader.join(timeout=2)
            while not output.empty():
                emit(output.get_nowait())
            for name in private_files:
                (folder / name).unlink(missing_ok=True)
