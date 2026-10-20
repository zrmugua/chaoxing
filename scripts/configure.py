"""Create a private environment file using Python's standard library."""

import argparse
import base64
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description="生成 Web 平台首次部署配置")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    token = secrets.token_urlsafe(32)
    content = (f"MASTER_KEY={key}\nSETUP_TOKEN={token}\nDATA_DIR=./data\n"
               "COOKIE_SECURE=true\nPORT=8080\n")
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, f"配置已存在：{args.output}；请保留原有 MASTER_KEY。\n")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print(f"已创建：{args.output.resolve()}")
    print("首次访问控制台时，从此文件读取 SETUP_TOKEN 并创建管理员。")
    print("请将 .env 与数据备份一同安全保管。")


if __name__ == "__main__":
    main()
