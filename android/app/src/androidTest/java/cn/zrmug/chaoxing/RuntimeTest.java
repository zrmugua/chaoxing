package cn.zrmug.chaoxing;

import android.app.Activity;
import android.content.*;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import java.io.*;
import java.net.URL;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.TimeUnit;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class RuntimeTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    private String cookie, csrf;

    private HttpURLConnection connect(String path, String method, JSONObject body) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:8080/api/" + path).openConnection();
        connection.setRequestMethod(method); connection.setConnectTimeout(1500); connection.setReadTimeout(3000);
        if (cookie != null) connection.setRequestProperty("Cookie", cookie);
        if (csrf != null) connection.setRequestProperty("X-CSRF-Token", csrf);
        if (body != null) {
            connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
            try (OutputStream output = connection.getOutputStream()) { output.write(body.toString().getBytes(StandardCharsets.UTF_8)); }
        }
        return connection;
    }
    private JSONObject json(HttpURLConnection connection) throws Exception {
        try (InputStream input = connection.getInputStream()) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            return new JSONObject(new String(output.toByteArray(), StandardCharsets.UTF_8));
        } finally { connection.disconnect(); }
    }
    private void status(String path, String method, JSONObject body, int expected) throws Exception {
        HttpURLConnection connection = connect(path, method, body);
        try { assertEquals(path, expected, connection.getResponseCode()); }
        finally { connection.disconnect(); }
    }
    private JSONObject selection(JSONArray courses, long revision) throws Exception {
        return new JSONObject().put("course_ids", courses).put("revision", revision);
    }
    private JSONObject learningAction(String path, String action, long revision) throws Exception {
        return json(connect(path + "/action", "POST", new JSONObject().put("action", action).put("revision", revision)));
    }
    private void assertSelection(JSONObject snapshot, int... expected) throws Exception {
        JSONArray actual = snapshot.getJSONArray("selected_course_ids");
        assertEquals(actual.toString(), expected.length, actual.length());
        for (int id : expected) {
            boolean found = false;
            for (int i = 0; i < actual.length(); i++) found |= actual.getInt(i) == id;
            assertTrue("Missing selected course " + id + " in " + actual, found);
        }
    }
    private void ready() throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(100);
        while (System.nanoTime() < deadline) {
            try {
                HttpURLConnection connection = connect("health", "GET", null);
                int result = connection.getResponseCode(); connection.disconnect();
                if (result == 200) return;
            } catch (Exception ignored) { }
            Thread.sleep(500);
        }
        fail("HTTP server did not start: " + RuntimeState.read(context));
    }
    @Test public void authenticationPersistenceAndAccountIsolation() throws Exception {
        Activity activity = InstrumentationRegistry.getInstrumentation().startActivitySync(
                new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        ConsoleService.requestStart(context); ready();
        HttpURLConnection unauthenticated = connect("accounts", "GET", null);
        assertEquals(401, unauthenticated.getResponseCode()); unauthenticated.disconnect();
        SecretStore configuration = new SecretStore(context);
        JSONObject login = new JSONObject().put("username", "apk-test").put("password", "android-test-password-long");
        JSONObject before = json(connect("auth/status", "GET", null));
        HttpURLConnection setup = connect(before.getBoolean("initialized") ? "auth/login" : "auth/setup", "POST",
                before.getBoolean("initialized") ? login : new JSONObject(login.toString()).put("setup_token", configuration.setupToken));
        assertEquals(200, setup.getResponseCode());
        String header = setup.getHeaderField("Set-Cookie");
        assertFalse(header.contains("Secure")); assertTrue(header.contains("HttpOnly")); assertTrue(header.contains("SameSite=strict"));
        cookie = header.split(";", 2)[0]; csrf = json(setup).getString("csrf");
        JSONObject added = json(connect("accounts", "POST", new JSONObject().put("label", "Android 验收账号")
                .put("username", "android-fixture-user").put("password", "android-fixture-secret")));
        assertTrue(added.getInt("id") > 0);
        int accountId = added.getInt("id");
        JSONObject other = json(connect("accounts", "POST", new JSONObject().put("label", "Android 课程隔离账号")
                .put("username", "android-other-fixture-user").put("password", "android-other-fixture-secret")));
        int otherAccountId = other.getInt("id");
        String learningPath = "accounts/" + accountId + "/learning";
        JSONObject emptyLearning = json(connect(learningPath, "GET", null));
        assertEquals(accountId, emptyLearning.getJSONObject("account").getInt("id"));
        assertEquals(0, emptyLearning.getJSONArray("courses").length());
        assertSelection(emptyLearning);
        for (String field : new String[] {"revision", "state", "desired_state", "message", "worker_online",
                "active_course_titles", "running_course_titles", "latest_activity", "current_task_id"}) {
            assertTrue("Missing learning snapshot field " + field, emptyLearning.has(field));
        }
        status(learningPath + "/action", "POST", new JSONObject().put("action", "start")
                .put("revision", emptyLearning.getLong("revision")), 409);
        JSONObject dashboard = json(connect("dashboard", "GET", null)); assertTrue(dashboard.getBoolean("worker_online"));
        File[] databaseFiles = new File(context.getFilesDir(), "data").listFiles();
        assertNotNull(databaseFiles);
        for (File file : databaseFiles) {
            if (file.getName().startsWith("console.sqlite3")) {
                try {
                    assertFalse(new String(Files.readAllBytes(file.toPath()), StandardCharsets.ISO_8859_1).contains("android-fixture-secret"));
                } catch (java.nio.file.NoSuchFileException error) {
                    // SQLite may remove WAL/SHM sidecars when its last connection closes.
                    if (file.getName().equals("console.sqlite3")) throw error;
                }
            }
        }
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        com.chaquo.python.PyObject scope = Python.getInstance().getModule("builtins").callAttr("dict");
        scope.callAttr("__setitem__", "native_dir", context.getApplicationInfo().nativeLibraryDir);
        scope.callAttr("__setitem__", "test_dir", new File(context.getFilesDir(), "native-test").getAbsolutePath());
        scope.callAttr("__setitem__", "model_dir", new File(context.getFilesDir(), "bundle/models").getAbsolutePath());
        scope.callAttr("__setitem__", "data_dir", new File(context.getFilesDir(), "data").getAbsolutePath());
        scope.callAttr("__setitem__", "master_key", configuration.masterKey);
        scope.callAttr("__setitem__", "account_id", accountId);
        scope.callAttr("__setitem__", "other_account_id", otherAccountId);
        Python.getInstance().getModule("builtins").callAttr("exec",
                "from pathlib import Path\n" +
                "from backend.app.db import Database\n" +
                "from backend.app.services import PlatformService\n" +
                "from backend.app.android.runtime import AndroidVault\n" +
                "fixture_db = Database(Path(data_dir) / 'console.sqlite3')\n" +
                "fixture_service = PlatformService(fixture_db, AndroidVault(master_key))\n" +
                "fixture_service.save_courses(account_id, [\n" +
                "    {'courseId': 'android-course-a', 'clazzId': 'android-class-a', 'title': 'Android 课程甲'},\n" +
                "    {'courseId': 'android-course-b', 'clazzId': 'android-class-b', 'title': 'Android 课程乙'}])\n" +
                "fixture_service.save_courses(other_account_id, [\n" +
                "    {'courseId': 'android-course-c', 'clazzId': 'android-class-c', 'title': 'Android 隔离课程'}])\n" +
                "first_course_id = fixture_db.one('SELECT id FROM courses WHERE account_id=? AND remote_id=?', (account_id, 'android-course-a'))['id']\n" +
                "second_course_id = fixture_db.one('SELECT id FROM courses WHERE account_id=? AND remote_id=?', (account_id, 'android-course-b'))['id']\n" +
                "other_course_id = fixture_db.one('SELECT id FROM courses WHERE account_id=?', (other_account_id,))['id']\n",
                scope);
        int firstCourseId = scope.callAttr("__getitem__", "first_course_id").toInt();
        int secondCourseId = scope.callAttr("__getitem__", "second_course_id").toInt();
        int otherCourseId = scope.callAttr("__getitem__", "other_course_id").toInt();
        JSONObject learning = json(connect(learningPath, "GET", null));
        assertEquals(2, learning.getJSONArray("courses").length());
        long initialRevision = learning.getLong("revision");
        status(learningPath, "PUT", selection(new JSONArray().put(otherCourseId), initialRevision), 409);
        learning = json(connect(learningPath, "PUT", selection(new JSONArray().put(firstCourseId).put(secondCourseId), initialRevision)));
        assertSelection(learning, firstCourseId, secondCourseId);
        assertTrue(learning.getLong("revision") > initialRevision);
        status(learningPath, "PUT", selection(new JSONArray(), initialRevision), 409);
        status(learningPath + "/action", "POST", new JSONObject().put("action", "stop").put("revision", initialRevision), 409);
        JSONObject unchanged = json(connect(learningPath, "GET", null));
        assertEquals(learning.getLong("revision"), unchanged.getLong("revision"));
        assertSelection(unchanged, firstCourseId, secondCourseId);
        learning = json(connect(learningPath, "PUT", selection(new JSONArray(), unchanged.getLong("revision"))));
        assertSelection(learning);
        status(learningPath + "/action", "POST", new JSONObject().put("action", "start")
                .put("revision", learning.getLong("revision")), 409);
        learning = json(connect(learningPath, "PUT", selection(new JSONArray().put(firstCourseId), learning.getLong("revision"))));
        learning = learningAction(learningPath, "pause", learning.getLong("revision"));
        assertEquals("paused", learning.getString("state"));
        assertEquals("paused", learning.getString("desired_state"));
        assertSelection(learning, firstCourseId);
        long persistedRevision = learning.getLong("revision");
        assertSelection(json(connect("accounts/" + otherAccountId + "/learning", "GET", null)));
        Python.getInstance().getModule("builtins").callAttr("exec",
                "from pathlib import Path\n" +
                "from types import SimpleNamespace\n" +
                "from backend.app.console_process import ConsoleProcess\n" +
                "from backend.app.android.resources import prepare_resources, LEGACY_RESOURCES\n" +
                "cfg = SimpleNamespace(data_dir=Path(test_dir), console_binary=native_dir + '/libyatori_console.so', onnx_library=native_dir + '/libonnxruntime.so', model_dir=model_dir)\n" +
                "legacy = cfg.data_dir / 'console/1/assets'\n" +
                "legacy.mkdir(parents=True, exist_ok=True)\n" +
                "for name in LEGACY_RESOURCES: (legacy / name).write_bytes(b'old generated cache')\n" +
                "prepare_resources(cfg.data_dir, Path(model_dir))\n" +
                "logs = []\n" +
                "for account in (1, 2):\n" +
                "    result = ConsoleProcess(cfg).run(account, {}, '', [], lambda: None, lambda line, level: logs.append(line), 'selftest')\n" +
                "    assert result['execution'] == 'yatori-go-console' and result['os'] == 'android'\n" +
                "    assert result['models_checked'] == 3\n" +
                "    assert not any((cfg.data_dir / 'console' / str(account) / 'assets' / name).exists() for name in LEGACY_RESOURCES)\n" +
                "    assert not (cfg.data_dir / 'console' / str(account) / 'config.yaml').exists()\n" +
                "    assert not (cfg.data_dir / 'console' / str(account) / 'query-result.json').exists()\n" +
                "ConsoleProcess(cfg).run(3, {'setting': {'basicSetting': {'logLevel': 'INFO'}}, 'users': []}, '', [], lambda: None, lambda line, level: logs.append(line))\n" +
                "assert any('请先在config文件中配置好相应账号' in line for line in logs)\n" +
                "import time, subprocess\n" +
                "children = []\n" +
                "real_spawn = subprocess.Popen\n" +
                "def spawn(*a, **kw):\n" +
                "    assert kw.get('pass_fds'), 'Console child must inherit its account ownership descriptor'\n" +
                "    child = real_spawn(*a, **kw)\n" +
                "    children.append(child)\n" +
                "    return child\n" +
                "deadline = time.monotonic() + 0.5\n" +
                "def stop():\n" +
                "    if time.monotonic() > deadline: raise RuntimeError('test cancellation')\n" +
                "subprocess.Popen = spawn\n" +
                "try:\n" +
                "    try: ConsoleProcess(cfg, ['/system/bin/sleep', '30']).run(4, {}, '', [], stop, lambda *a: None)\n" +
                "    except RuntimeError: pass\n" +
                "    assert len(children) == 1 and children[0].poll() is not None\n" +
                "    assert not (cfg.data_dir / 'console/4/config.yaml').exists()\n" +
                "finally: subprocess.Popen = real_spawn\n",
                scope);
        Python.getInstance().getModule("builtins").callAttr("exec",
                "import os, signal, threading, tempfile\n" +
                "from backend.app.config import Config\n" +
                "from backend.app.worker import Worker\n" +
                "from backend.app.account_learning import AccountLearning\n" +
                "with tempfile.TemporaryDirectory(prefix='learning-', dir=test_dir) as isolated_dir:\n" +
                "    isolated_cfg = Config(Path(isolated_dir), master_key, 'android-fixture-setup-token', vault_factory=AndroidVault)\n" +
                "    calls = []\n" +
                "    next_action = 'pause'\n" +
                "    class FixtureProcess:\n" +
                "        def __init__(self, config): pass\n" +
                "        def run(self, account, value, proxy, secrets, control, log, mode, course):\n" +
                "            assert mode is None and course is None\n" +
                "            assert value['users'][0]['coursesCustom']['includeCourses'] == ['Android 生命周期课程']\n" +
                "            calls.append(account)\n" +
                "            log('[Android 生命周期课程] 正在学习该课程', 'info')\n" +
                "            current = flow.snapshot(account)\n" +
                "            assert current['state'] == 'running'\n" +
                "            assert current['running_course_titles'] == ['Android 生命周期课程']\n" +
                "            flow.action(account, next_action, current['revision'])\n" +
                "            control()\n" +
                "            raise AssertionError('Lifecycle change must interrupt the Console process')\n" +
                "    isolated_worker = Worker(isolated_cfg, FixtureProcess)\n" +
                "    isolated_service = isolated_worker.service\n" +
                "    isolated_account = isolated_worker.db.execute('INSERT INTO accounts(label,credentials,created_at) VALUES(?,?,?)', ('Android 生命周期账号', isolated_worker.vault.seal({'username': 'android-lifecycle-fixture', 'password': 'android-lifecycle-fixture-secret'}), time.time()))\n" +
                "    isolated_service.save_courses(isolated_account, [{'courseId': 'lifecycle-course', 'clazzId': 'lifecycle-class', 'title': 'Android 生命周期课程'}])\n" +
                "    flow = AccountLearning(isolated_service)\n" +
                "    state = flow.snapshot(isolated_account)\n" +
                "    course_ids = [state['courses'][0]['id']]\n" +
                "    state = flow.save(isolated_account, course_ids, state['revision'])\n" +
                "    state = flow.action(isolated_account, 'start', state['revision'])\n" +
                "    isolated_worker.run_task(isolated_worker.claim())\n" +
                "    state = flow.snapshot(isolated_account)\n" +
                "    assert state['state'] == state['desired_state'] == 'paused'\n" +
                "    assert state['selected_course_ids'] == course_ids\n" +
                "    assert state['running_course_titles'] == [] and state['active_course_titles'] == []\n" +
                "    next_action = 'stop'\n" +
                "    state = flow.action(isolated_account, 'resume', state['revision'])\n" +
                "    isolated_worker.run_task(isolated_worker.claim())\n" +
                "    state = flow.snapshot(isolated_account)\n" +
                "    assert state['state'] == state['desired_state'] == 'stopped'\n" +
                "    assert state['selected_course_ids'] == course_ids and len(calls) == 2\n" +
                "    assert isolated_worker.claim() is None\n" +
                "ownership_folder = cfg.data_dir / 'console/5'\n" +
                "ownership_folder.mkdir(parents=True, exist_ok=True)\n" +
                "orphan_pid_file = ownership_folder / 'orphan.pid'\n" +
                "orphan_pid_file.unlink(missing_ok=True)\n" +
                "shell = None\n" +
                "orphan_pid = None\n" +
                "replacement = None\n" +
                "waiting = threading.Event()\n" +
                "ownership_results, ownership_errors = [], []\n" +
                "checks = [0]\n" +
                "def ownership_control():\n" +
                "    checks[0] += 1\n" +
                "    if checks[0] >= 3: waiting.set()\n" +
                "def replace_owner():\n" +
                "    try: ownership_results.append(ConsoleProcess(cfg).run(5, {}, '', [], ownership_control, lambda *a: None, 'selftest'))\n" +
                "    except BaseException as error: ownership_errors.append(error)\n" +
                "try:\n" +
                "    with ConsoleProcess.ownership(ownership_folder, lambda: None) as descriptor:\n" +
                "        shell = subprocess.Popen(['/system/bin/sh', '-c', 'sleep 30 & echo $! > orphan.pid; wait'], cwd=ownership_folder, pass_fds=(descriptor,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n" +
                "        deadline = time.monotonic() + 5\n" +
                "        while not orphan_pid_file.exists() and time.monotonic() < deadline: time.sleep(0.02)\n" +
                "        assert orphan_pid_file.exists()\n" +
                "        orphan_pid = int(orphan_pid_file.read_text())\n" +
                "        shell.kill()\n" +
                "        shell.wait(timeout=3)\n" +
                "    (ownership_folder / 'config.yaml').write_text('current owner')\n" +
                "    replacement = threading.Thread(target=replace_owner, daemon=True)\n" +
                "    replacement.start()\n" +
                "    assert waiting.wait(5) and replacement.is_alive()\n" +
                "    assert (ownership_folder / 'config.yaml').read_text() == 'current owner'\n" +
                "    os.kill(orphan_pid, signal.SIGTERM)\n" +
                "    orphan_pid = None\n" +
                "    replacement.join(timeout=20)\n" +
                "    assert not replacement.is_alive(), 'Account directory ownership was not released'\n" +
                "    assert not ownership_errors, str(ownership_errors)\n" +
                "    assert ownership_results[0]['models_checked'] == 3\n" +
                "    assert not (ownership_folder / 'config.yaml').exists()\n" +
                "finally:\n" +
                "    if shell and shell.poll() is None:\n" +
                "        shell.kill()\n" +
                "        shell.wait(timeout=3)\n" +
                "    if orphan_pid is not None:\n" +
                "        try: os.kill(orphan_pid, signal.SIGTERM)\n" +
                "        except ProcessLookupError: pass\n" +
                "    if replacement: replacement.join(timeout=5)\n" +
                "    orphan_pid_file.unlink(missing_ok=True)\n",
                scope);
        DevicePreferences.set(context, "desired_running", false);
        context.stopService(new Intent(context, ConsoleService.class));
        for (int attempt = 0; attempt < 60 && !"已停止".equals(RuntimeState.read(context)); attempt++) Thread.sleep(250);
        assertEquals("已停止", RuntimeState.read(context));
        Thread.sleep(500);
        ConsoleService.requestStart(context); ready();
        assertEquals(configuration.masterKey, new SecretStore(context).masterKey);
        HttpURLConnection relogin = connect("auth/login", "POST", login);
        assertEquals(200, relogin.getResponseCode()); relogin.disconnect();
        HttpURLConnection saved = connect("accounts", "GET", null);
        assertEquals(200, saved.getResponseCode()); saved.disconnect();
        JSONObject restoredLearning = json(connect(learningPath, "GET", null));
        assertSelection(restoredLearning, firstCourseId);
        assertTrue(restoredLearning.getLong("revision") > persistedRevision);
        assertEquals("paused", restoredLearning.getString("state"));
        assertEquals("paused", restoredLearning.getString("desired_state"));
        status(learningPath, "PUT", selection(new JSONArray().put(secondCourseId), persistedRevision), 409);
        JSONObject stoppedLearning = learningAction(learningPath, "stop", restoredLearning.getLong("revision"));
        assertEquals("stopped", stoppedLearning.getString("state"));
        assertEquals("stopped", stoppedLearning.getString("desired_state"));
        assertSelection(stoppedLearning, firstCourseId);
        status("accounts/" + accountId, "DELETE", null, 200);
        status("accounts/" + otherAccountId, "DELETE", null, 200);
        context.stopService(new Intent(context, ConsoleService.class));
        InstrumentationRegistry.getInstrumentation().runOnMainSync(activity::finish);
    }
}
