"""Create a consistent SQLite snapshot with the online backup API."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description="备份 Web 平台 SQLite 数据库")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", "data")))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.data_dir / "console.sqlite3"
    if not source.is_file():
        parser.error(f"数据库不存在：{source}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or args.data_dir / "backups" / f"console-{stamp}.sqlite3"
    if output.resolve() == source.resolve():
        parser.error("备份目标必须与数据库源文件不同")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error(f"备份目标已存在：{output}")
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(output)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("SQLite 完整性检查未通过")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    print(f"已备份：{output.resolve()}")
    print("恢复时需要匹配的 MASTER_KEY；请另外安全备份 .env。")


if __name__ == "__main__":
    main()
