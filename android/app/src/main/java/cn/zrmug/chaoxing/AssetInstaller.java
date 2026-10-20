package cn.zrmug.chaoxing;

import android.content.Context;
import android.content.res.AssetManager;
import java.io.*;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;

public final class AssetInstaller {
    public static File install(Context context) throws Exception {
        File root = new File(context.getFilesDir(), "bundle");
        String version = context.getPackageManager().getPackageInfo(context.getPackageName(), 0).lastUpdateTime + "";
        File stamp = new File(context.getFilesDir(), "bundle.version");
        try (RandomAccessFile lockFile = new RandomAccessFile(new File(context.getFilesDir(), "bundle.lock"), "rw");
             FileLock ignored = lockFile.getChannel().lock()) {
            if (!stamp.isFile() || !version.equals(new String(java.nio.file.Files.readAllBytes(stamp.toPath()), StandardCharsets.UTF_8))) {
                copy(context.getAssets(), "console", root);
                java.nio.file.Files.write(stamp.toPath(), version.getBytes(StandardCharsets.UTF_8));
            }
        }
        return root;
    }

    private static void copy(AssetManager assets, String source, File destination) throws IOException {
        String[] children = assets.list(source);
        if (children != null && children.length > 0) {
            if (!destination.isDirectory() && !destination.mkdirs()) throw new IOException("Asset directory unavailable");
            for (String child : children) copy(assets, source + "/" + child, new File(destination, child));
        } else {
            try (InputStream input = assets.open(source); OutputStream output = new FileOutputStream(destination)) {
                byte[] buffer = new byte[32768]; int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            }
        }
    }
}
