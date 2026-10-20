"""Build the Yatori Android AAR using the pinned gomobile toolchain."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default=shutil.which("go"))
    args = parser.parse_args()
    if not args.go:
        parser.error("Install Go 1.27 or provide --go")
    for name in ("JAVA_HOME", "ANDROID_HOME", "ANDROID_NDK_HOME"):
        if not os.environ.get(name):
            parser.error(name + " must point to the installed build dependency")
    go = str(Path(args.go).resolve())
    tools = ROOT / ".tools/android-go-bin"
    tools.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "GOBIN": str(tools)}
    environment["PATH"] = os.pathsep.join([str(Path(go).parent), str(tools),
        str(Path(environment["JAVA_HOME"]) / "bin"), environment.get("PATH", "")])
    def run(command):
        return subprocess.run(command, cwd=ROOT / "engine", env=environment, check=True)
    version = subprocess.check_output([go, "list", "-m", "-f", "{{.Version}}", "golang.org/x/mobile"],
                                      cwd=ROOT / "engine", env=environment, text=True).strip()
    for name in ("gomobile", "gobind"):
        run([go, "install", "golang.org/x/mobile/cmd/" + name + "@" + version])
    mobile = str(tools / ("gomobile.exe" if os.name == "nt" else "gomobile"))
    run([mobile, "init"])
    output = ROOT / "android/app/libs/yatori-engine.aar"
    output.parent.mkdir(parents=True, exist_ok=True)
    run([mobile, "bind", "-target=android/arm,android/arm64,android/amd64", "-androidapi", "26",
         "-trimpath", "-ldflags=-s -w", "-o", str(output), "./mobile"])
    print("Yatori Android library built: " + str(output))


if __name__ == "__main__":
    main()
