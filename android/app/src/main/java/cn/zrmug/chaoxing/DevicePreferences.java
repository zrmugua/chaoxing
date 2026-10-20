package cn.zrmug.chaoxing;

import android.content.Context;
import android.util.AtomicFile;
import org.json.JSONObject;
import java.io.*;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;

/** Fresh, atomic settings shared by the activity, boot receiver and server process. */
public final class DevicePreferences {
    private static synchronized boolean access(Context context, String key, Boolean update) {
        try (RandomAccessFile lockFile = new RandomAccessFile(new File(context.getFilesDir(), "preferences.lock"), "rw");
             FileLock ignored = lockFile.getChannel().lock()) {
            AtomicFile file = new AtomicFile(new File(context.getFilesDir(), "preferences.json"));
            JSONObject values = new JSONObject();
            if (file.getBaseFile().exists() || new File(file.getBaseFile().getPath() + ".bak").exists())
                values = new JSONObject(new String(file.readFully(), StandardCharsets.UTF_8));
            if (update == null) return values.optBoolean(key, false);
            values.put(key, update);
            FileOutputStream output = file.startWrite();
            try {
                output.write(values.toString().getBytes(StandardCharsets.UTF_8)); file.finishWrite(output);
            } catch (Exception error) { file.failWrite(output); throw error; }
            return update;
        } catch (Exception error) { throw new IllegalStateException("Device preferences unavailable"); }
    }
    public static boolean get(Context context, String key) { return access(context, key, null); }
    public static void set(Context context, String key, boolean value) { access(context, key, value); }
}
