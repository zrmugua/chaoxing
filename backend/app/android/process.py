"""Adapt Android bound services to the core adapter's pipe protocol."""
import json
import subprocess
import threading


class AndroidProcess:
    def __init__(self, *args, **kwargs):
        from java import jclass
        try:
            self.session = jclass("cn.zrmug.chaoxing.AdapterPool").open()
        except Exception:
            raise OSError("Android adapter unavailable") from None
        self.stdin = self
        self.stdout = self
        self._pending = ""
        self._closed = False
        self._write_lock = threading.Lock()

    def _call(self, method, *arguments):
        try:
            return getattr(self.session, method)(*arguments)
        except Exception:
            raise OSError("Android adapter disconnected") from None

    def write(self, text):
        with self._write_lock:
            self._pending += text
            while "\n" in self._pending:
                line, self._pending = self._pending.split("\n", 1)
                if len(line.encode("utf-8")) > 1_999_999:
                    raise OSError("RPC request exceeds limit")
                self._call("send", line)

    def flush(self):
        pass

    def readline(self, size=-1):
        while not self._closed:
            result = self._call("poll", 250)
            if result is not None:
                text = str(result)
                if json.loads(text).get("dead"):
                    return ""
                return text + "\n"
            if not self._call("isAlive"):
                return ""
        return ""

    def poll(self):
        return None if not self._closed and self._call("isAlive") else 0

    def kill(self):
        self.close()

    def wait(self, timeout=None):
        if not self._call("awaitDeath", int((timeout or 5) * 1000)):
            raise subprocess.TimeoutExpired("android-adapter", timeout)
        return 0

    def close(self):
        if not self._closed:
            self._closed = True
            self._call("close")
