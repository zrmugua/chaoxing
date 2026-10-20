package cn.zrmug.chaoxing;

import android.content.Context;
import android.util.AtomicFile;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileLock;
import org.json.JSONObject;

public final class RuntimeState {
    private static synchronized String access(Context context, String update) {
        try (RandomAccessFile lockFile = new RandomAccessFile(new File(context.getFilesDir(), "runtime.lock"), "rw");
             FileLock ignored = lockFile.getChannel().lock()) {
            AtomicFile file = new AtomicFile(new File(context.getFilesDir(), "runtime.json"));
            if (update != null) {
                FileOutputStream output = file.startWrite();
                try {
                    output.write(new JSONObject().put("status", update).put("updated_at", System.currentTimeMillis()).toString().getBytes(StandardCharsets.UTF_8));
                    file.finishWrite(output);
                } catch (Exception error) { file.failWrite(output); throw error; }
                return update;
            }
            if (!file.getBaseFile().exists() && !new File(file.getBaseFile().getPath() + ".bak").exists()) return "已停止";
            JSONObject state = new JSONObject(new String(file.readFully(), StandardCharsets.UTF_8));
            String status = state.getString("status");
            if ("运行中".equals(status) && System.currentTimeMillis() - state.getLong("updated_at") > 20000)
                return "服务未响应，请重新启动";
            return status;
        } catch (Exception error) { return "状态暂时无法读取"; }
    }
    public static void write(Context context, String status) { access(context, status); }
    public static String read(Context context) { return access(context, null); }
}
