package cn.zrmug.chaoxing;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Standard Fernet tokens, interoperable with the Web platform's Vault. */
public final class FernetCipher {
    private final byte[] signingKey;
    private final byte[] encryptionKey;

    public FernetCipher(String encodedKey) {
        byte[] key = Base64.getUrlDecoder().decode(encodedKey);
        if (key.length != 32) throw new IllegalArgumentException("Invalid encryption key");
        signingKey = Arrays.copyOfRange(key, 0, 16);
        encryptionKey = Arrays.copyOfRange(key, 16, 32);
        Arrays.fill(key, (byte) 0);
    }

    private byte[] mac(byte[] value) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(signingKey, "HmacSHA256"));
        return mac.doFinal(value);
    }

    public String encrypt(String value) throws Exception {
        byte[] iv = new byte[16];
        new SecureRandom().nextBytes(iv);
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(encryptionKey, "AES"), new IvParameterSpec(iv));
        byte[] ciphertext = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
        ByteBuffer content = ByteBuffer.allocate(25 + ciphertext.length);
        content.put((byte) 0x80).putLong(System.currentTimeMillis() / 1000).put(iv).put(ciphertext);
        byte[] signed = content.array();
        ByteBuffer token = ByteBuffer.allocate(signed.length + 32).put(signed).put(mac(signed));
        return Base64.getUrlEncoder().encodeToString(token.array());
    }

    public String decrypt(String value) throws Exception {
        byte[] token = Base64.getUrlDecoder().decode(value);
        if (token.length < 73 || token[0] != (byte) 0x80 || (token.length - 57) % 16 != 0)
            throw new IllegalArgumentException("Invalid encrypted value");
        byte[] signed = Arrays.copyOf(token, token.length - 32);
        if (!MessageDigest.isEqual(mac(signed), Arrays.copyOfRange(token, token.length - 32, token.length)))
            throw new IllegalArgumentException("Invalid encrypted value");
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(encryptionKey, "AES"),
                new IvParameterSpec(Arrays.copyOfRange(token, 9, 25)));
        byte[] plaintext = cipher.doFinal(Arrays.copyOfRange(token, 25, token.length - 32));
        return new String(plaintext, StandardCharsets.UTF_8);
    }
}
