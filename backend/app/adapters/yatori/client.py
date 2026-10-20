"""Account-scoped RPC client for the pinned Yatori execution engine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from dataclasses import asdict
from typing import Callable

from ..contracts import AdapterError, Job
from ...security import redact


ERROR_MESSAGES = {
    "manual_required": "学习通要求人工处理，请在学习通确认后继续。",
    "login_failed": "学习通登录未通过，请检查账号或人工验证状态。",
    "session_expired": "学习通会话已失效，请重新验证账号。",
    "parser_changed": "Yatori 返回数据无法转换为任务信息，请检查接口兼容性。",
    "jobs_missing": "章节仍有任务点，但学习通未返回可识别的任务，请同步核对进度。",
    "job_state_unknown": "任务点完成状态缺少依据，请在学习通核对后同步。",
    "network_error": "连接学习通失败，请稍后重试。",
    "remote_error": "学习通未确认本次操作成功。",
    "unsupported_job": "该任务类型需要在学习通中处理。",
    "blocked_destination": "学习通返回了允许范围之外的请求地址。",
    "execution_timeout": "任务达到执行时限，请核对进度后恢复。",
    "core_unavailable": "Yatori 执行核心不可用，请检查核心构建或安装。",
    "adapter_error": "Yatori 执行进程异常，已保留任务状态。",
}
RETRYABLE_CODES = {"network_error", "remote_error", "execution_timeout"}
OPERATION_LABELS = {
    "initialize": "初始化学习通适配器", "login": "验证学习通登录",
    "list_courses": "读取课程列表", "list_chapters": "读取章节列表",
    "list_jobs": "读取章节任务点", "execute": "执行任务点",
    "questions": "解析章节测验", "export_cookies": "保存学习通会话",
    "list_assessments": "读取课程作业与考试",
    "chapter_paper": "读取章节测验试卷", "assessment_questions": "读取作业或考试试卷",
    "save_answers": "保存或提交答案", "chaoxing_answer": "请求学习通 AI",
}


class YatoriAdapter:
    """One native engine process per account operation or worker task.

    Credentials travel through an anonymous stdin pipe. The child owns the Yatori account cache and sends structured results, progress and console events.
    """

    def __init__(self, credentials: dict, cookies: list[dict] | None = None,
                 control: Callable[[], None] | None = None, process_factory=None,
                 log_callback: Callable[[str, str], None] | None = None):
        self._control = control or (lambda: None)
        self._log_callback = log_callback
        self._log_secrets = {str(value) for key, value in credentials.items() if key in ("username", "password", "proxy_url") and value}
        self._remember_log_cookies(cookies or [])
        self._messages: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._sequence = 0
        self._closed = False
        self._process = None
        self._timeout = min(max(float(credentials.get("execution_timeout", 28800)), 30), 86400)
        root = Path(__file__).resolve().parents[4]
        engine = os.environ.get("YATORI_ENGINE", str(root / "bin" / ("yatori-engine.exe" if os.name == "nt" else "yatori-engine")))
        env = os.environ.copy()
        env.pop("MASTER_KEY", None)
        env.pop("SETUP_TOKEN", None)
        env["PYTHONPATH"] = str(root)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            self._process = (process_factory or subprocess.Popen)(
                [engine],
                cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            threading.Thread(target=self._read_results, daemon=True).start()
            if getattr(self._process, "stderr", None) is not None:
                threading.Thread(target=self._read_stderr, daemon=True).start()
            self.engine_info = self._rpc("initialize", {"credentials": credentials, "cookies": cookies or []})
            if not isinstance(self.engine_info, dict) or self.engine_info.get("engine") != "yatori":
                raise AdapterError("core_unavailable", ERROR_MESSAGES["core_unavailable"])
        except AdapterError:
            self.close()
            raise
        except (OSError, subprocess.SubprocessError):
            self.close()
            raise AdapterError("core_unavailable", ERROR_MESSAGES["core_unavailable"]) from None

    def _read_results(self):
        try:
            while True:
                line = self._process.stdout.readline(2_000_001)
                if not line or len(line) > 2_000_000:
                    break
                try:
                    message = json.loads(line)
                except (ValueError, TypeError):
                    break
                if not isinstance(message, dict):
                    break
                if message.get("event") == "log":
                    self._console_log(message.get("message"))
                    continue
                self._messages.put(message)
        except (OSError, ValueError):
            pass
        finally:
            self._messages.put(None)

    def _remember_log_cookies(self, cookies):
        # Short flags and numeric identifiers are filtered by field, preserving diagnostics.
        self._log_secrets.update(str(cookie["value"]) for cookie in cookies
                                 if len(str(cookie.get("value", ""))) >= 8)

    def _console_log(self, text):
        if not self._log_callback or not isinstance(text, str):
            return
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        text = redact(text, tuple(self._log_secrets), limit=66000)
        if text:
            match = re.search(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|PANIC)\b", text, re.I)
            level = match.group(1).lower() if match else "info"
            level = {"warn": "warning", "fatal": "error", "panic": "error"}.get(level, level)
            self._log_callback(text, level)

    def _read_stderr(self):
        try:
            for line in self._process.stderr:
                self._console_log(line.rstrip("\r\n"))
        except (OSError, ValueError):
            pass

    def _rpc(self, operation: str, arguments: dict | None = None,
             control: Callable[[], None] | None = None,
             progress: Callable[[float], None] | None = None):
        with self._lock:
            if self._closed:
                raise AdapterError("adapter_error", ERROR_MESSAGES["adapter_error"])
            self._sequence += 1
            request_id = self._sequence
            request_sent = False
            try:
                self._control()
                if control:
                    control()
                # A partial pipe write can already have reached the engine.
                request_sent = True
                self._process.stdin.write(json.dumps({"id": request_id, "op": operation,
                                                      "args": arguments or {}}, ensure_ascii=False) + "\n")
                self._process.stdin.flush()
                started = time.monotonic()
                timeout = self._timeout if operation == "execute" else 180
                while True:
                    self._control()
                    if control:
                        control()
                    if time.monotonic() - started >= timeout:
                        raise AdapterError("execution_timeout", ERROR_MESSAGES["execution_timeout"], True)
                    try:
                        result = self._messages.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if result is None:
                        raise AdapterError("adapter_error", ERROR_MESSAGES["adapter_error"])
                    if result.get("id") != request_id:
                        raise AdapterError("adapter_error", ERROR_MESSAGES["adapter_error"])
                    if result.get("event") == "progress":
                        if progress:
                            progress(max(0, min(1, float(result.get("value", 0)))))
                        continue
                    if not result.get("ok"):
                        code = result.get("code")
                        if code not in ERROR_MESSAGES:
                            code = "adapter_error"
                        stage = OPERATION_LABELS.get(operation, "学习通操作")
                        card_index = result.get("card_index")
                        if type(card_index) is int and 0 <= card_index <= 10000:
                            stage += f"（第 {card_index + 1} 张任务卡）"
                        raise AdapterError(code, f"{stage}：{ERROR_MESSAGES[code]}", code in RETRYABLE_CODES)
                    data = result.get("data")
                    if operation == "export_cookies" and isinstance(data, list):
                        self._remember_log_cookies(data)
                    return data
            except AdapterError:
                self.close()
                raise
            except (BrokenPipeError, OSError, ValueError):
                self.close()
                raise AdapterError("adapter_error", ERROR_MESSAGES["adapter_error"]) from None
            except BaseException as error:
                error.rpc_request_sent = request_sent
                self.close()
                raise

    def login(self, username: str, password: str) -> None:
        self._rpc("login", {"username": username, "password": password})

    def list_courses(self) -> list[dict]:
        return self._rpc("list_courses")

    def list_chapters(self, course: dict) -> list[dict]:
        return self._rpc("list_chapters", {"course": course})

    def list_jobs(self, course: dict, chapter: dict) -> list[Job]:
        return [Job(**value) for value in self._rpc("list_jobs", {"course": course, "chapter": chapter})]

    def execute(self, course: dict, job: Job, control: Callable[[], None],
                progress: Callable[[float], None]) -> None:
        self._rpc("execute", {"course": course, "job": asdict(job)}, control, progress)

    def questions(self, course: dict, job: Job) -> list[dict]:
        return self._rpc("questions", {"course": course, "job": asdict(job)})

    def export_cookies(self) -> list[dict]:
        return self._rpc("export_cookies")

    def list_assessments(self, course: dict, work=True, exam=True) -> list[dict]:
        return self._rpc("list_assessments", {"course":course, "work":work, "exam":exam})

    def chapter_paper(self, course: dict, job: Job) -> dict:
        return self._rpc("chapter_paper", {"course": course, "job": asdict(job)})

    def assessment_questions(self, course: dict, assessment: dict) -> dict:
        return self._rpc("assessment_questions", {"course": course, "assessment": assessment})

    def save_answers(self, paper_id: str, answers: dict, submit=False, require_complete=False) -> dict:
        return self._rpc("save_answers", {"paper_id": paper_id, "answers": answers,
                                          "submit": submit, "require_complete": require_complete})

    def chaoxing_answer(self, course: dict, question: dict) -> str:
        return self._rpc("chaoxing_answer", {"course": course, "question": question})["answer"]

    def close(self) -> None:
        self._closed = True
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for stream in (process.stdin, process.stdout, getattr(process, "stderr", None)):
            if stream:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
