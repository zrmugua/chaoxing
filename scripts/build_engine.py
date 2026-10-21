"""Build the pinned Yatori engine for the host platform."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default=shutil.which("go"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.go:
        parser.error("Install Go 1.27 or pass --go with its executable path")
    subprocess.run([os.sys.executable, str(ROOT / "scripts/vendor_yatori.py")], check=True)
    subprocess.run([os.sys.executable, str(ROOT / "scripts/verify_yatori_console.py")], check=True)
    output = args.output or ROOT / "bin" / ("yatori-engine.exe" if os.name == "nt" else "yatori-engine")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pin = json.loads((ROOT / "engine/upstream.json").read_text(encoding="utf-8"))["commit"]
    subprocess.run([str(Path(args.go).resolve()), "build", "-trimpath", "-ldflags",
                    "-s -w -X chaoxing-console/engine/runtime.UpstreamCommit=" + pin,
                    "-o", str(output), "./cmd/yatori-engine"], cwd=ROOT / "engine",
                   env={**os.environ, "CGO_ENABLED": "0"}, check=True)
    print("Yatori engine built: " + str(output))


if __name__ == "__main__":
    main()
