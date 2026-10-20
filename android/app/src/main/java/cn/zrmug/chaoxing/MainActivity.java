package cn.zrmug.chaoxing;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.widget.*;
import java.util.List;

public final class MainActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status, addresses;
    private LinearLayout content;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(RuntimeState.read(MainActivity.this));
            List<String> values = LocalNetwork.addresses();
            StringBuilder links = new StringBuilder();
            for (String address : values) links.append("http://").append(address).append(":").append(ConsoleService.PORT).append("\n");
            addresses.setText(links.length() == 0 ? "连接 Wi-Fi 或开启设备热点后查看地址" : links.toString().trim());
            handler.postDelayed(this, 1500);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(248, 250, 252));
        content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); content.setPadding(dp(24), dp(30), dp(24), dp(30));
        scroll.addView(content); setContentView(scroll);
        text("CHAOXING CONSOLE", 11, 0xff64748b, true);
        text("学习通管理台", 28, 0xff0f172a, true);
        text("在本机运行，通过局域网浏览器管理。", 14, 0xff64748b, false);
        status = text("已停止", 18, 0xff2563eb, true);
        button("启动服务", () -> {
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
            try { ConsoleService.requestStart(this); }
            catch (RuntimeException error) { toast("系统暂时无法启动服务，请重试"); }
        });
        button("停止服务", () -> {
            DevicePreferences.set(this, "desired_running", false);
            stopService(new Intent(this, ConsoleService.class));
        });
        Switch auto = new Switch(this); auto.setText("开机后恢复已启动的服务"); auto.setTextColor(0xff334155);
        auto.setPadding(0, dp(12), 0, dp(16)); auto.setChecked(DevicePreferences.get(this, "auto_start"));
        auto.setOnCheckedChangeListener((view, value) -> DevicePreferences.set(this, "auto_start", value));
        content.addView(auto);
        text("局域网访问地址", 15, 0xff0f172a, true);
        addresses = text("等待网络连接", 15, 0xff2563eb, false); addresses.setTextIsSelectable(true);
        button("复制访问地址", () -> copy("访问地址", addresses.getText().toString()));
        text("首次连接", 15, 0xff0f172a, true);
        text("手机或电脑连接同一局域网，在浏览器打开上方地址，填写初始化令牌并创建管理员账号。", 13, 0xff64748b, false);
        button("查看初始化令牌", () -> {
            try {
                String token = new SecretStore(this).setupToken;
                new AlertDialog.Builder(this).setTitle("初始化令牌").setMessage(token + "\n\n在网页首次设置时填写，并创建管理员账号。")
                        .setPositiveButton("复制", (dialog, which) -> copy("初始化令牌", token)).setNegativeButton("关闭", null).show();
            } catch (Exception error) { toast("设备配置无法读取，请保留应用数据并检查系统状态"); }
        });
        text("保持服务运行时会显示常驻通知。任务、账号和运行记录保存在应用内，升级安装会保留；卸载应用会清除。", 12, 0xff64748b, false);
        button("源代码与许可证", () -> {
            if (BuildConfig.SOURCE_URL.isEmpty()) {
                new AlertDialog.Builder(this).setTitle("源代码与许可证")
                    .setMessage("本应用按 GPL-3.0 分发，Yatori 核心保留 MIT 许可证。对应源码和构建说明随安装包提供。")
                    .setPositiveButton("关闭", null).show();
                return;
            }
            try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.SOURCE_URL))); }
            catch (ActivityNotFoundException error) { copy("源代码地址", BuildConfig.SOURCE_URL); }
        });
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setPadding(0, dp(7), 0, dp(8)); view.setLineSpacing(dp(3), 1);
        if (bold) view.setTypeface(null, Typeface.BOLD);
        content.addView(view); return view;
    }
    private void button(String title, Runnable action) {
        Button view = new Button(this); view.setText(title); view.setTextSize(14); view.setAllCaps(false); view.setTextColor(Color.WHITE);
        GradientDrawable background = new GradientDrawable(); background.setColor(0xff2563eb); background.setCornerRadius(dp(8));
        view.setBackground(background); LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(46)); params.setMargins(0, dp(6), 0, dp(7));
        content.addView(view, params); view.setOnClickListener(ignored -> action.run());
    }
    private void copy(String label, String value) {
        ((ClipboardManager) getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText(label, value)); toast("已复制");
    }
    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }
    @Override public void onResume() {
        super.onResume(); handler.post(refresh);
        if (getIntent().getBooleanExtra("start_service", false)) {
            getIntent().removeExtra("start_service");
            try { ConsoleService.requestStart(this); }
            catch (RuntimeException error) { toast("系统暂时无法启动服务，请重试"); }
        }
    }
    @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
