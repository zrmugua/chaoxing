package cn.zrmug.chaoxing;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import java.io.*;

/** Local device-owner diagnostics for UFI/ADB. */
public final class DeviceStatusProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    private void owner() {
        int uid = Binder.getCallingUid();
        if (uid != 0 && uid != 2000 && uid != android.os.Process.myUid()) throw new SecurityException("Device owner access required");
    }
    @Override public Bundle call(String method, String arg, Bundle extras) {
        owner(); Bundle result = new Bundle();
        try {
            if ("status".equals(method)) {
                result.putString("status", RuntimeState.read(getContext()));
                result.putString("setup_token", new SecretStore(getContext()).setupToken);
                result.putStringArrayList("addresses", new java.util.ArrayList<>(LocalNetwork.addresses()));
                result.putInt("http_port", ConsoleService.PORT);
            } else if ("auto_start".equals(method)) {
                DevicePreferences.set(getContext(), "auto_start", "true".equals(arg));
                result.putBoolean("ok", true);
            } else throw new IllegalArgumentException("Unknown operation");
        } catch (Exception error) { result.putString("error", "设备配置无法读取"); }
        return result;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        owner(); throw new FileNotFoundException();
    }
    @Override public String getType(Uri uri) { return null; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) { throw new UnsupportedOperationException(); }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
