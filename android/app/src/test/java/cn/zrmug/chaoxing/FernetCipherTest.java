package cn.zrmug.chaoxing;

import org.junit.Test;
import java.util.Base64;
import static org.junit.Assert.*;

public class FernetCipherTest {
    private FernetCipher cipher() {
        byte[] key = new byte[32]; for (int i = 0; i < key.length; i++) key[i] = (byte) i;
        return new FernetCipher(Base64.getUrlEncoder().encodeToString(key));
    }
    @Test public void unicodeRoundTripAndRandomizedTokens() throws Exception {
        FernetCipher cipher = cipher(); String value = "{\"课程\":\"账号隔离\"}";
        String first = cipher.encrypt(value), second = cipher.encrypt(value);
        assertEquals(value, cipher.decrypt(first)); assertNotEquals(first, second);
    }
    @Test public void tamperedTokenIsRejectedBeforeDecrypting() throws Exception {
        String token = cipher().encrypt("fixture"); byte[] bytes = Base64.getUrlDecoder().decode(token); bytes[30] ^= 1;
        try { cipher().decrypt(Base64.getUrlEncoder().encodeToString(bytes)); fail("Tampered token accepted"); }
        catch (IllegalArgumentException expected) { }
    }
    @Test public void invalidKeyIsRejected() {
        try { new FernetCipher(Base64.getUrlEncoder().encodeToString(new byte[16])); fail("Invalid key accepted"); }
        catch (IllegalArgumentException expected) { }
    }
}
