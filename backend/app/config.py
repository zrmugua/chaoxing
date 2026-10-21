import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class Config:
    data_dir: Path
    master_key: str
    setup_token: str
    secure_cookie: bool = True
    web_dir: Path = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    vault_factory: Callable[[str], Any] | None = None
    lan_only: bool = False
    session_cookie: str = "study_session"
    console_binary: str = os.environ.get("YATORI_CONSOLE_BINARY", "bin/yatori-console.exe" if os.name == "nt" else "bin/yatori-console")
    onnx_library: str = os.environ.get("YATORI_ONNX_LIBRARY", "")
    model_dir: str = os.environ.get("YATORI_MODEL_DIR", "")

    @classmethod
    def from_env(cls):
        key = os.environ.get("MASTER_KEY", "")
        token = os.environ.get("SETUP_TOKEN", "")
        if not key or len(token) < 24:
            raise RuntimeError("请先运行 scripts/configure.py，配置 MASTER_KEY 与 SETUP_TOKEN")
        return cls(Path(os.environ.get("DATA_DIR", "data")), key, token,
                   os.environ.get("COOKIE_SECURE", "true").lower() == "true")
