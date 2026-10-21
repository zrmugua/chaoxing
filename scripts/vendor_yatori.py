"""Import and verify the pinned Yatori Go dependency closure used by the engine."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "third_party/yatori-go-core"
PIN = ROOT / "engine/upstream.json"
PREFIX = "github.com/yatori-dev/yatori-go-core/"

HOOK = '''// Platform request boundary, maintained by the management platform.
package xuexitong

import (
    "net/http"
    "net/url"
    "strings"
)

var ConsoleRequestHook func(*http.Client, *http.Request) (*http.Response, error)

func platformDo(client *http.Client, request *http.Request) (*http.Response, error) {
    if ConsoleRequestHook != nil { return ConsoleRequestHook(client, request) }
    return client.Do(request)
}

func platformPostForm(client *http.Client, endpoint string, values url.Values) (*http.Response, error) {
    request, err := http.NewRequest("POST", endpoint, strings.NewReader(values.Encode()))
    if err != nil { return nil, err }
    request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
    return platformDo(client, request)
}
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def verify():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    for name, item in pin["files"].items():
        if digest(normalized(DEST / name)) != item["packaged_sha256"]:
            raise SystemExit("Yatori source differs from the reviewed manifest: " + name)
    actual = {p.relative_to(DEST).as_posix() for p in DEST.rglob("*") if p.is_file()}
    if actual != set(pin["files"]):
        raise SystemExit("Yatori source file list differs from the reviewed manifest")
    print(f"Yatori source verified: {len(actual)} files, {pin['commit']}")


def import_source(source, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("An exact reviewed upstream commit is required")
    if PIN.exists():
        verify()
    pending, packages, files = ["api/xuexitong"], set(), {}
    while pending:
        package = pending.pop()
        if package in packages:
            continue
        packages.add(package)
        directory = source / package
        if not directory.is_dir():
            raise SystemExit("Missing upstream package: " + package)
        for file in sorted(directory.glob("*.go")):
            raw = normalized(file)
            text = raw.decode("utf-8")
            name = file.relative_to(source).as_posix()
            packaged = text
            if name == "utils/YatoriCoreInit.go":
                # This desktop resource initializer embeds OCR/Node assets.
                # The platform initializes its own account-scoped runtime.
                packaged = "//go:build ignore\n\n" + packaged
            elif not name.endswith("_test.go"):
                pending.extend(re.findall(r'"' + re.escape(PREFIX) + r'([^"\s]+)"', text))
                if package == "api/xuexitong":
                    packaged = packaged.replace("client.Do(", "platformDo(client, ")
                    packaged = packaged.replace("client.PostForm(", "platformPostForm(client, ")
                    # The platform transport classifies active verification before
                    # returning HTML; preserve original checks for standalone use.
                    packaged = packaged.replace(
                        'if strings.Contains(string(body), "请输入验证码") || strings.Contains(string(body), "请输入图片中的验证码") {',
                        'if ConsoleRequestHook == nil && (strings.Contains(string(body), "请输入验证码") || strings.Contains(string(body), "请输入图片中的验证码")) {')
            files[name] = (raw, packaged.encode("utf-8"))
    for name in ["go.mod", "go.sum", "LICENSE"]:
        raw = normalized(source / name)
        files[name] = (raw, raw)
    files["api/xuexitong/platform_transport.go"] = (None, HOOK.encode())
    manifest = {"repository": "https://github.com/yatori-dev/yatori-go-core", "commit": commit,
                "license": "MIT", "packages": sorted(packages), "files": {}}
    DEST.mkdir(parents=True, exist_ok=True)
    previous = {p.relative_to(DEST).as_posix() for p in DEST.rglob("*") if p.is_file()}
    for name in sorted(previous - files.keys()):
        (DEST / name).unlink()
    for name, (raw, packaged) in sorted(files.items()):
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(packaged)
        manifest["files"][name] = {"upstream_sha256": digest(raw) if raw is not None else None,
                                   "packaged_sha256": digest(packaged)}
    PIN.parent.mkdir(parents=True, exist_ok=True)
    PIN.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    if args.source:
        import_source(args.source.resolve(), args.commit or "")
    else:
        verify()


if __name__ == "__main__":
    main()
