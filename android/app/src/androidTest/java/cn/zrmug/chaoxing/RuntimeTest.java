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
        Python.getInstance().getModule("builtins").callAttr("exec",
                "from pathlib import Path\n" +
                "from types import SimpleNamespace\n" +
                "from backend.app.console_process import ConsoleProcess\n" +
                "cfg = SimpleNamespace(data_dir=Path(test_dir), console_binary=native_dir + '/libyatori_console.so', onnx_library=native_dir + '/libonnxruntime.so')\n" +
                "logs = []\n" +
                "for account in (1, 2):\n" +
                "    result = ConsoleProcess(cfg).run(account, {}, '', [], lambda: None, lambda line, level: logs.append(line), 'selftest')\n" +
                "    assert result['execution'] == 'yatori-go-console' and result['os'] == 'android'\n" +
                "    assert not (cfg.data_dir / 'console' / str(account) / 'config.yaml').exists()\n" +
                "    assert not (cfg.data_dir / 'console' / str(account) / 'query-result.json').exists()\n" +
                "ConsoleProcess(cfg).run(3, {'setting': {'basicSetting': {'logLevel': 'INFO'}}, 'users': []}, '', [], lambda: None, lambda line, level: logs.append(line))\n" +
                "assert any('请先在config文件中配置好相应账号' in line for line in logs)\n" +
                "import time, subprocess\n" +
                "children = []\n" +
                "real_spawn = subprocess.Popen\n" +
                "def spawn(*a, **kw):\n" +
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
        context.stopService(new Intent(context, ConsoleService.class));
        InstrumentationRegistry.getInstrumentation().runOnMainSync(activity::finish);
    }
}
