"""Launch the local Web service or Worker from the project root."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.umask(0o077)
if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

parser = argparse.ArgumentParser(description="启动学习通 Web 平台")
parser.add_argument("--worker", action="store_true")
parser.add_argument("--dev-cookie", action="store_true", help="本地 HTTP 调试使用 Cookie")
parser.add_argument("--port", type=int, default=8080)
args = parser.parse_args()
if args.dev_cookie:
    os.environ["COOKIE_SECURE"] = "false"
if args.worker:
    from backend.app.worker import main
    main()
else:
    import uvicorn
    uvicorn.run("backend.app.main:create_app", factory=True, host="127.0.0.1", port=args.port,
                access_log=False, log_level="warning")
