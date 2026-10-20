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
    private JSONObject rpc(AdapterPool.Session session, int id, String operation, JSONObject arguments) throws Exception {
        session.send(new JSONObject().put("id", id).put("op", operation).put("args", arguments).toString());
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
        while (System.nanoTime() < deadline) {
            String line = session.poll(500);
            if (line == null) continue;
            JSONObject result = new JSONObject(line);
            assertFalse("Adapter process disconnected", result.optBoolean("dead"));
            if (result.has("event")) continue;
            assertEquals(id, result.getInt("id"));
            assertTrue("Core RPC failed: " + result.optString("code"), result.getBoolean("ok"));
            return result;
        }
        throw new AssertionError("Core RPC timed out");
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
            if (file.getName().startsWith("console.sqlite3"))
                assertFalse(new String(Files.readAllBytes(file.toPath()), StandardCharsets.ISO_8859_1).contains("android-fixture-secret"));
        }
        AdapterPool.initialize(context);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        Python.getInstance().getModule("builtins").callAttr("exec",
                "from backend.app.adapters.yatori import YatoriAdapter\n" +
                "from backend.app.android.process import AndroidProcess\n" +
                "with YatoriAdapter({}, [], process_factory=AndroidProcess) as adapter:\n" +
                "    assert adapter.export_cookies() == []\n",
                Python.getInstance().getModule("builtins").callAttr("dict"));
        AdapterPool.Session first = AdapterPool.open(), second = AdapterPool.open();
        try {
            assertNotEquals(first.processId(), second.processId());
            for (AdapterPool.Session session : new AdapterPool.Session[]{first, second}) {
                String marker = session == first ? "first-isolated-account" : "second-isolated-account";
                JSONArray cookies = new JSONArray().put(new JSONObject().put("name", "_uid").put("value", marker).put("domain", ".chaoxing.com"));
                JSONObject initialized = rpc(session, 1, "initialize", new JSONObject().put("credentials", new JSONObject()).put("cookies", cookies));
                assertEquals("yatori", initialized.getJSONObject("data").getString("engine"));
                String exported = rpc(session, 2, "export_cookies", new JSONObject()).getJSONArray("data").toString();
                assertTrue(exported.contains(marker));
                assertFalse(exported.contains(session == first ? "second-isolated-account" : "first-isolated-account"));
            }
        } finally { first.close(); second.close(); }
        assertFalse(first.isAlive()); assertFalse(second.isAlive());
        assertTrue(first.awaitDeath(3000)); assertTrue(second.awaitDeath(3000));
        AdapterPool.Session fresh = AdapterPool.open();
        try {
            rpc(fresh, 1, "initialize", new JSONObject().put("credentials", new JSONObject()));
            assertEquals(0, rpc(fresh, 2, "export_cookies", new JSONObject()).getJSONArray("data").length());
        } finally { fresh.close(); }
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
