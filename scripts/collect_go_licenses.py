"""Collect license texts for packages linked into the Yatori runtime."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default=shutil.which("go"))
    args = parser.parse_args()
    if not args.go:
        parser.error("Go is required")
    go = str(Path(args.go).resolve())
    def command(*values):
        return subprocess.check_output([go, *values], cwd=ROOT / "engine", text=True, encoding="utf-8")
    raw = command("list", "-deps", "-json", "./runtime", "./mobile")
    modules = {}
    decoder = json.JSONDecoder()
    while raw.strip():
        raw = raw.lstrip()
        package, length = decoder.raw_decode(raw)
        raw = raw[length:]
        module = package.get("Module") or {}
        module = module.get("Replace", module)
        if module.get("Dir") and not module.get("Main"):
            modules[module["Dir"]] = module.get("Path", "")
    mobile = json.loads(command("list", "-m", "-json", "golang.org/x/mobile"))
    modules[mobile["Dir"]] = mobile["Path"]
    modules[command("env", "GOROOT").strip()] = "Go standard library"
    texts = []
    for directory, name in sorted(modules.items(), key=lambda item: item[1]):
        path = Path(directory)
        files = [p for p in path.iterdir() if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT"))]
        if not files:
            raise SystemExit("License text missing for " + name)
        for file in sorted(files):
            texts.append(name + " / " + file.name + "\n" + "=" * 72 + "\n" + file.read_text(encoding="utf-8") + "\n")
    output = ROOT / "engine/licenses/THIRD_PARTY_GO_LICENSES.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(texts).rstrip() + "\n", encoding="utf-8")
    print(f"Collected {len(texts)} license texts for {len(modules)} Go modules")


if __name__ == "__main__":
    main()
