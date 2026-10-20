package cn.zrmug.chaoxing;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class SecretStore {
    private static final String ALIAS = "chaoxing-console-config-v1";
    public final String masterKey;
    public final String setupToken;

    public SecretStore(Context context) throws Exception {
        synchronized (SecretStore.class) {
            try (RandomAccessFile lockFile = new RandomAccessFile(new File(context.getFilesDir(), "config.lock"), "rw");
                 FileLock ignored = lockFile.getChannel().lock()) {
                AtomicFile file = new AtomicFile(new File(context.getFilesDir(), "config.enc"));
                JSONObject config;
                if (file.getBaseFile().exists() || new File(file.getBaseFile().getPath() + ".bak").exists()) {
                    config = new JSONObject(new String(unwrap(file.readFully(), "config-v1"), StandardCharsets.UTF_8));
                } else {
                    byte[] key = new byte[32];
                    byte[] token = new byte[32];
                    SecureRandom random = new SecureRandom();
                    random.nextBytes(key); random.nextBytes(token);
                    config = new JSONObject().put("master_key", Base64.getUrlEncoder().encodeToString(key))
                            .put("setup_token", Base64.getUrlEncoder().withoutPadding().encodeToString(token));
                    byte[] encrypted = wrap(config.toString().getBytes(StandardCharsets.UTF_8), "config-v1");
                    FileOutputStream stream = file.startWrite();
                    try { stream.write(encrypted); file.finishWrite(stream); }
                    catch (Exception error) { file.failWrite(stream); throw error; }
                }
                masterKey = config.getString("master_key");
                setupToken = config.getString("setup_token");
            }
        }
    }

    private static synchronized SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }

    public static byte[] wrap(byte[] plaintext, String domain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key()); cipher.updateAAD(domain.getBytes(StandardCharsets.UTF_8));
        byte[] ciphertext = cipher.doFinal(plaintext);
        byte[] output = Arrays.copyOf(cipher.getIV(), 12 + ciphertext.length);
        System.arraycopy(ciphertext, 0, output, 12, ciphertext.length); return output;
    }

    public static byte[] unwrap(byte[] encrypted, String domain) throws Exception {
        if (encrypted.length < 28) throw new IllegalArgumentException("Invalid configuration");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Arrays.copyOf(encrypted, 12)));
        cipher.updateAAD(domain.getBytes(StandardCharsets.UTF_8));
        return cipher.doFinal(Arrays.copyOfRange(encrypted, 12, encrypted.length));
    }
}
