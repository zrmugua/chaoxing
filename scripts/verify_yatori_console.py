"""Verify the reviewed Console service adaptation and its source provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console-source", type=Path)
    parser.add_argument("--core-source", type=Path)
    args = parser.parse_args()
    pin = json.loads((ROOT / "engine/console-upstream.json").read_text(encoding="utf-8"))
    for name, expected in pin["adapted_files"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise SystemExit("Console adaptation differs from the reviewed manifest: " + name)
    actual = {file.relative_to(ROOT).as_posix() for file in (ROOT / "engine/consolelogic").glob("*.go") if not file.name.endswith("_test.go")}
    expected = {name for name in pin["adapted_files"] if name.startswith("engine/consolelogic/")}
    if actual != expected:
        raise SystemExit("Console adaptation file list differs from the reviewed manifest")
    runner = (ROOT / "engine/consolelogic/runner.go").read_text(encoding="utf-8")
    if re.search(r'const Commit = "([0-9a-f]{40})"', runner).group(1) != pin["console"]["commit"]:
        raise SystemExit("Console runtime commit differs from its source record")
    for key, source in (("console", args.console_source), ("core", args.core_source)):
        if source:
            for name, record in pin[key]["files"].items():
                if digest(source / name) != record["sha256"]:
                    raise SystemExit("Upstream source differs from the reviewed record: " + name)
    print("Yatori Console adaptation verified: " + pin["console"]["commit"])


if __name__ == "__main__":
    main()
