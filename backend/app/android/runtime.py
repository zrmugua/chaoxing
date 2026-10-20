"""LAN HTTP console and persistent Worker hosted by an Android foreground service."""
from functools import partial
import json
import os
from pathlib import Path
import threading

from ..config import Config

_worker = None
_server = None
_threads = []


class AndroidVault:
    def __init__(self, key):
        from java import jclass
        self.cipher = jclass("cn.zrmug.chaoxing.FernetCipher")(key)

    def seal(self, value):
        return str(self.cipher.encrypt(json.dumps(value, ensure_ascii=False)))

    def open(self, value):
        return json.loads(str(self.cipher.decrypt(value)))


def start(data_dir, asset_dir, master_key, setup_token, port):
    global _worker, _server, _threads
    if _server is not None:
        raise RuntimeError("服务已启动")
    os.umask(0o077)
    data_dir, asset_dir = Path(str(data_dir)), Path(str(asset_dir))
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)
    from ..main import create_app
    from ..worker import Worker
    from ..adapters.yatori import YatoriAdapter
    from .process import AndroidProcess
    import uvicorn
    config = Config(data_dir, str(master_key), str(setup_token), False,
                    asset_dir / "web", vault_factory=AndroidVault, lan_only=True,
                    session_cookie="study_android_session")
    app = create_app(config)
    if not app.state.db.one("SELECT value FROM settings WHERE key='android_configured'"):
        app.state.db.set_setting("concurrency", 1)
        app.state.db.set_setting("android_configured", True)
    _worker = Worker(config, partial(YatoriAdapter, process_factory=AndroidProcess))
    server_config = uvicorn.Config(app, host="0.0.0.0", port=int(port), loop="asyncio", http="h11",
                                  ws="none", lifespan="off", access_log=False, log_level="critical",
                                  proxy_headers=False, timeout_graceful_shutdown=8)
    _server = uvicorn.Server(server_config)

    def serve_web():
        import asyncio
        asyncio.run(_server.serve())

    _threads = [threading.Thread(target=serve_web, name="console-web", daemon=True),
                threading.Thread(target=_worker.serve, name="console-worker", daemon=True)]
    for thread in _threads:
        thread.start()
    return True


def stop():
    if _worker:
        _worker.shutdown.set()
    if _server:
        _server.should_exit = True
    for thread in _threads:
        thread.join(timeout=8)
    return not any(thread.is_alive() for thread in _threads)
