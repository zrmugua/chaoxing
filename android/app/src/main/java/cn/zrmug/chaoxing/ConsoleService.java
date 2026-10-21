package cn.zrmug.chaoxing;

import android.app.*;
import android.content.*;
import android.os.*;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import java.io.*;
import java.net.URL;
import java.net.HttpURLConnection;
import java.util.concurrent.*;

public final class ConsoleService extends Service {
    public static final String START = "cn.zrmug.chaoxing.START", STOP = "cn.zrmug.chaoxing.STOP";
    public static final int PORT = 8080;
    private final ExecutorService lifecycle = Executors.newSingleThreadExecutor();
    private final ScheduledExecutorService monitor = Executors.newSingleThreadScheduledExecutor();
    private volatile boolean stopping;
    private boolean started;
    private PowerManager.WakeLock wakeLock;

    public static void requestStart(Context context) {
        DevicePreferences.set(context, "desired_running", true);
        context.startForegroundService(new Intent(context, ConsoleService.class).setAction(START));
    }
    private void status(String value) { RuntimeState.write(this, value); }

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager notifications = getSystemService(NotificationManager.class);
        notifications.createNotificationChannel(new NotificationChannel("console", "学习管理服务", NotificationManager.IMPORTANCE_LOW));
        PendingIntent show = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, ConsoleService.class).setAction(STOP), PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, "console").setSmallIcon(R.drawable.ic_console)
                .setContentTitle("学习通管理服务").setContentText("局域网控制台与后台任务正在运行")
                .setContentIntent(show).setOngoing(true).addAction(new Notification.Action.Builder(null, "停止服务", stop).build()).build();
        startForeground(1, notification);
        wakeLock = ((PowerManager) getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "chaoxing:server");
        wakeLock.acquire();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && STOP.equals(intent.getAction())) {
            DevicePreferences.set(this, "desired_running", false);
            stopSelf(); return START_NOT_STICKY;
        }
        if (!started && !stopping) {
            started = true; status("正在启动"); lifecycle.submit(this::startRuntime);
        }
        return START_STICKY;
    }

    private void startRuntime() {
        try {
            SecretStore secrets = new SecretStore(this);
            File assets = AssetInstaller.install(this);
            if (stopping) return;
            if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
            File data = new File(getFilesDir(), "data");
            Python.getInstance().getModule("backend.app.android.runtime").callAttr("start", data.getAbsolutePath(), assets.getAbsolutePath(),
                    secrets.masterKey, secrets.setupToken, PORT, getApplicationInfo().nativeLibraryDir);
            for (int attempt = 0; attempt < 90 && !stopping; attempt++) {
                try {
                    HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:" + PORT + "/api/health").openConnection();
                    connection.setConnectTimeout(700); connection.setReadTimeout(700);
                    int code = connection.getResponseCode(); connection.disconnect();
                    if (code == 200) {
                        status("运行中");
                        monitor.scheduleWithFixedDelay(this::checkHealth, 5, 5, TimeUnit.SECONDS);
                        return;
                    }
                } catch (IOException ignored) { }
                Thread.sleep(500);
            }
            if (!stopping) throw new IOException("Startup timed out");
        } catch (Exception error) {
            if (BuildConfig.DEBUG) android.util.Log.e("ConsoleRuntime", "Runtime start failed", error);
            if (!stopping) {
                status("启动失败：请检查设备兼容性或端口占用");
                DevicePreferences.set(this, "desired_running", false);
                stopSelf();
            }
        }
    }

    private void checkHealth() {
        if (stopping) return;
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL("http://127.0.0.1:" + PORT + "/api/health").openConnection();
            connection.setConnectTimeout(1500); connection.setReadTimeout(1500);
            if (connection.getResponseCode() == 200) status("运行中");
        } catch (Exception ignored) { }
        finally { if (connection != null) connection.disconnect(); }
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onDestroy() {
        stopping = true;
        monitor.shutdownNow();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        stopForeground(STOP_FOREGROUND_REMOVE);
        lifecycle.submit(() -> {
            try {
                if (Python.isStarted()) Python.getInstance().getModule("backend.app.android.runtime").callAttr("stop");
            } catch (Exception ignored) { }
            if (!RuntimeState.read(this).startsWith("启动失败")) status("已停止");
            android.os.Process.killProcess(android.os.Process.myPid());
        });
        lifecycle.shutdown();
        super.onDestroy();
    }
}
