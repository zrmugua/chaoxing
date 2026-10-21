"""Build the pinned, original Yatori Console program for Android."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "engine/original-console.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    source = ROOT / "third_party/yatori-go-console"
    for name, expected in pin["files"].items():
        data = (source / name).read_bytes()
        if name.endswith(".go") or name in ("go.mod", "go.sum", "LICENSE"):
            data = data.replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit("Original Console source changed: " + name)
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    if actual != set(pin["files"]):
        raise SystemExit("Original Console source file list changed")
    return pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default=shutil.which("go"))
    parser.add_argument("--host", action="store_true", help="Build a native desktop/server Console")
    parser.add_argument("--ndk")
    parser.add_argument("--abis", default="armeabi-v7a,arm64-v8a,x86_64")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    pin = verify_sources()
    if args.verify:
        print("Original Console source verified: " + pin["commit"])
        return
    if not args.go:
        parser.error("Go is required")
    go = str(Path(args.go).resolve())
    cache = ROOT / ".tools/original-console-build"
    source = cache / "console"
    shutil.copytree(ROOT / "third_party/yatori-go-console", source, dirs_exist_ok=True)
    shutil.copyfile(ROOT / "engine/console_bridge/query.go", source / "bridge_query.go")

    def module(name):
        output = subprocess.check_output([go, "mod", "download", "-json", name], cwd=source)
        data = json.loads(output)
        if data.get("Error"):
            raise SystemExit(data["Error"])
        return Path(data["Dir"])

    ocr_source = module("github.com/Changbaiqi/ddddocr-go@" + pin["ocr_version"])
    ocr = cache / "ddddocr"
    shutil.copytree(ocr_source, ocr, dirs_exist_ok=True)
    for path in ocr.rglob("*"):
        if path.is_file():
            path.chmod(stat.S_IREAD | stat.S_IWRITE)
    linux = ocr / "utils/ocr_lib_linux.go"
    linux.write_text(linux.read_text(encoding="utf-8").replace("//go:build linux", "//go:build linux && !android"), encoding="utf-8")
    (ocr / "utils/ocr_lib_android.go").write_text('''//go:build android
package utils
import "embed"
//go:embed assets/common_old.onnx assets/common_tencent.onnx assets/calc_det.onnx
var assets embed.FS
func init() { sharedLibName = "libonnxruntime.so" }
''', encoding="utf-8")
    path = ocr / "utils/Init.go"
    text = path.read_text(encoding="utf-8")
    text = text.replace('os.WriteFile("./assets/"+sharedLibName, data, 0644)',
                        'if os.Getenv("YATORI_ONNX_LIBRARY") == "" { os.WriteFile("./assets/"+sharedLibName, data, 0644) }')
    text = text.replace('ort.SetSharedLibraryPath("./assets/" + sharedLibName)',
                        'library := os.Getenv("YATORI_ONNX_LIBRARY")\n if library == "" { library = "./assets/" + sharedLibName }\n ort.SetSharedLibraryPath(library)')
    path.write_text(text, encoding="utf-8")
    with (source / "go.mod").open("a", encoding="utf-8") as file:
        file.write("\nreplace github.com/Changbaiqi/ddddocr-go => " + ocr.as_posix() + "\n")
    if args.host:
        dest = ROOT / "bin" / ("yatori-console.exe" if os.name == "nt" else "yatori-console")
        dest.parent.mkdir(exist_ok=True)
        subprocess.run([go, "build", "-mod=readonly", "-tags=consolebridge", "-trimpath", "-ldflags=-s -w", "-o", str(dest), "."],
                       cwd=source, env={**os.environ, "CGO_ENABLED": "1"}, check=True)
        print("Original Console built: " + str(dest))
        return
    ndk = Path(args.ndk or os.environ["ANDROID_NDK_HOME"])
    archive = cache / "onnxruntime-android.aar"
    if not archive.exists():
        version = pin["onnx_android_version"]
        url = f"https://repo.maven.apache.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/{version}/onnxruntime-android-{version}.aar"
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    if sha(archive) != pin["onnx_android_sha256"]:
        raise SystemExit("ONNX Android archive digest mismatch")
    targets = {"armeabi-v7a": ("arm", "armv7a-linux-androideabi26"), "arm64-v8a": ("arm64", "aarch64-linux-android26"), "x86_64": ("amd64", "x86_64-linux-android26")}
    host = "windows-x86_64" if os.name == "nt" else "linux-x86_64"
    binaries = {}
    for abi in args.abis.split(","):
        arch, triple = targets[abi]
        compiler = ndk / "toolchains/llvm/prebuilt" / host / "bin" / (triple + "-clang" + (".cmd" if os.name == "nt" else ""))
        dest = ROOT / "android/app/libs/original-console" / abi
        dest.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "GOOS": "android", "GOARCH": arch, "GOARM": "7", "CGO_ENABLED": "1", "CC": str(compiler.resolve())}
        subprocess.run([go, "build", "-mod=readonly", "-tags=consolebridge", "-trimpath", "-buildmode=pie", "-ldflags=-s -w -extldflags=-Wl,-z,max-page-size=16384",
                        "-o", str(dest / "libyatori_console.so"), "."], cwd=source, env=environment, check=True)
        with ZipFile(archive) as package:
            (dest / "libonnxruntime.so").write_bytes(package.read("jni/" + abi + "/libonnxruntime.so"))
        binaries[abi] = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in dest.glob("*.so")}
        print("Original Console built: " + abi, flush=True)
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/original-console-build.json").write_text(json.dumps({"commit": pin["commit"],
        "bridge_sha256": sha(ROOT / "engine/console_bridge/query.go"), "binaries": binaries}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
