package cn.zrmug.chaoxing;

import android.content.*;

public final class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) && DevicePreferences.get(context, "auto_start")
                && DevicePreferences.get(context, "desired_running")) {
            try { ConsoleService.requestStart(context); }
            catch (RuntimeException error) { RuntimeState.write(context, "开机启动受系统限制，请手动启动"); }
        }
    }
}
