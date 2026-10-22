#!/usr/bin/env bash
# Run inside the emulator job so evidence is collected before emulator shutdown.
set -uo pipefail
mkdir -p artifacts/android-ci
result=0
adb push artifacts/console-tests/x86_64/bridge.test /data/local/tmp/console-bridge.test || result=1
adb shell chmod 755 /data/local/tmp/console-bridge.test || result=1
adb shell /data/local/tmp/console-bridge.test -test.v > artifacts/android-ci/bridge-tests.log 2>&1 || result=1
cat artifacts/android-ci/bridge-tests.log
if [ "$result" -ne 0 ]; then exit "$result"; fi
android/gradlew -p android :app:connectedEmulatorDebugAndroidTest --stacktrace || result=$?
if [ "$result" -eq 0 ]; then
  # Install the standalone app after the instrumentation runner's cleanup.
  adb install -r android/app/build/outputs/apk/emulator/debug/app-emulator-debug.apk || result=1
  adb shell am start -W -n cn.zrmug.chaoxing/.MainActivity --ez start_service true
  adb forward tcp:18080 tcp:8080
  ready=false
  for attempt in $(seq 1 60); do
    if curl --silent --fail --connect-timeout 1 --max-time 2 \
        http://127.0.0.1:18080/api/health > artifacts/android-ci/health.json; then
      ready=true
      break
    fi
    sleep 1
  done
  if [ "$ready" = true ]; then
    curl --silent --fail http://127.0.0.1:18080/ \
      > artifacts/android-ci/web.html || result=1
    python -c "from pathlib import Path; import json; assert json.loads(Path('artifacts/android-ci/health.json').read_text())['status']=='ok'; assert '<div id=\"app\"></div>' in Path('artifacts/android-ci/web.html').read_text()" || result=1
    status=$(curl --silent -o artifacts/android-ci/unauthenticated.json \
      -w '%{http_code}' http://127.0.0.1:18080/api/accounts)
    [ "$status" = 401 ] || result=1
  else
    result=1
  fi
fi
adb logcat -d -s AndroidRuntime ConsoleRuntime python.stderr > artifacts/android-ci/runtime.log || true
adb exec-out screencap -p > artifacts/android-ci/screen.png || true
exit "$result"
