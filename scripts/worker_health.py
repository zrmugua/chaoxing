"""Check the scheduler heartbeat without changing the database."""

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import time


def main():
    database = Path(os.environ.get("DATA_DIR", "data")) / "console.sqlite3"
    if not database.is_file():
        return 1
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
            row = conn.execute("SELECT heartbeat FROM runtime WHERE id=1").fetchone()
        return 0 if row and 0 <= time.time() - row[0] < 90 else 1
    except (sqlite3.Error, OSError, TypeError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
