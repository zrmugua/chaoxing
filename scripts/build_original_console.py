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
RESOURCE_PIN = ROOT / "engine/android-resources.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_module(original, target):
    # Generated build copies are confined to this task's build directory.
    assert target.resolve().parent == (ROOT / ".tools/original-console-build").resolve()
    if target.exists():
        for path in [target, *target.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        shutil.rmtree(target)
    shutil.copytree(original, target)
    for path in [target, *target.rglob("*")]:
        path.chmod(path.stat().st_mode | stat.S_IWRITE)


def verify_inputs(directory, records):
    for name, expected in records.items():
        data = (directory / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit("Android resource input changed: " + name)


def patch_android_resources(core, ocr):
    pin = json.loads(RESOURCE_PIN.read_text(encoding="utf-8"))
    verify_inputs(core, pin["core_files"])
    verify_inputs(ocr, pin["ocr_files"])
    path = core / "utils/YatoriCoreInit.go"
    text = path.read_text(encoding="utf-8")
    for name in ("tencentCollect.exe", "tencentPowSolve.exe"):
        text = text.replace("//go:embed assets/" + name + "\n", "").replace('\t"' + name + '",\n', "")
    path.write_text(text, encoding="utf-8")
    path = ocr / "utils/ocr_lib_linux.go"
    path.write_text(path.read_text(encoding="utf-8").replace("//go:build linux", "//go:build linux && !android"), encoding="utf-8")
    path = ocr / "utils/Init.go"
    path.write_text("//go:build !android\n\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copyfile(ROOT / "engine/android_resources/ocr_init.go", ocr / "utils/Init_android.go")
    for name, model in (("AutoVerification.go", "common_old.onnx"), ("AutoDetectionForTencent.go", "common_tencent.onnx"),
                        ("AutoDetctionForCalc.go", "calc_det.onnx")):
        path = ocr / "utils" / name
        text = path.read_text(encoding="utf-8")
        text = text.replace('"./assets/' + model + '"', 'modelPath("' + model + '")')
        path.write_text(text, encoding="utf-8")
    destination = ROOT / "android/app/libs/console-resources/models"
    destination.mkdir(parents=True, exist_ok=True)
    for name, record in pin["models"].items():
        path = ocr / "utils/assets" / name
        if sha(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
            raise SystemExit("Original OCR model changed: " + name)
        shutil.copyfile(path, destination / name)
    return pin["models"]


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
    parser.add_argument("--test-abi", choices=("armeabi-v7a", "arm64-v8a", "x86_64"),
                        help="Also compile bridge regression tests for this Android ABI")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.test_abi and (args.host or args.test_abi not in args.abis.split(",")):
        parser.error("--test-abi must be included in the Android --abis selection")
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
    shutil.copyfile(ROOT / "engine/console_bridge/chapter_status.go", source / "bridge_chapter_status.go")

    def module(name):
        output = subprocess.check_output([go, "mod", "download", "-json", name], cwd=source)
        data = json.loads(output)
        if data.get("Error"):
            raise SystemExit(data["Error"])
        return Path(data["Dir"])

    if args.host:
        dest = ROOT / "bin" / ("yatori-console.exe" if os.name == "nt" else "yatori-console")
        dest.parent.mkdir(exist_ok=True)
        subprocess.run([go, "build", "-mod=readonly", "-tags=consolebridge", "-trimpath", "-ldflags=-s -w", "-o", str(dest), "."],
                       cwd=source, env={**os.environ, "CGO_ENABLED": "1"}, check=True)
        print("Original Console built: " + str(dest))
        return
    ocr_source = module("github.com/Changbaiqi/ddddocr-go@" + pin["ocr_version"])
    core_source = module("github.com/yatori-dev/yatori-go-core@" + pin["core_version"])
    ocr, core = cache / "ddddocr", cache / "core"
    stage_module(ocr_source, ocr)
    stage_module(core_source, core)
    models = patch_android_resources(core, ocr)
    with (source / "go.mod").open("a", encoding="utf-8") as file:
        file.write("\nreplace github.com/Changbaiqi/ddddocr-go => " + ocr.as_posix() + "\n")
        file.write("replace github.com/yatori-dev/yatori-go-core => " + core.as_posix() + "\n")
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
        if args.test_abi == abi:
            test_binary = ROOT / "artifacts/console-tests" / abi / "bridge.test"
            test_binary.parent.mkdir(parents=True, exist_ok=True)
            test_sources = [ROOT / "engine/console_bridge" / name for name in
                            ("query.go", "chapter_status.go", "query_test.go", "chapter_status_test.go")]
            subprocess.run([go, "test", "-c", "-mod=readonly", "-tags=consolebridge", "-trimpath",
                            "-o", str(test_binary), *map(str, test_sources)], cwd=source, env=environment, check=True)
            print("Console bridge tests built: " + abi, flush=True)
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/original-console-build.json").write_text(json.dumps({"commit": pin["commit"],
        "bridge_sha256": sha(ROOT / "engine/console_bridge/query.go"), "models": models,
        "chapter_status_sha256": sha(ROOT / "engine/console_bridge/chapter_status.go"),
        "android_ocr_init_sha256": sha(ROOT / "engine/android_resources/ocr_init.go"), "binaries": binaries}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
