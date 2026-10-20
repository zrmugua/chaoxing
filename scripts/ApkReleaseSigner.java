import com.android.apksig.ApkSigner;
import com.android.apksig.ApkVerifier;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.*;
import java.security.cert.X509Certificate;
import java.util.*;

/** Sign an already aligned APK with a maintainer-owned PKCS12 identity. */
public final class ApkReleaseSigner {
    public static void main(String[] args) throws Exception {
        if (args.length != 4) throw new IllegalArgumentException("unsigned.apk signed.apk identity.p12 password-file");
        File output = new File(args[1]);
        if (output.exists()) throw new IOException("Output already exists");
        char[] password = Files.readString(new File(args[3]).toPath(), StandardCharsets.UTF_8).strip().toCharArray();
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = new FileInputStream(args[2])) { store.load(input, password); }
        String alias = store.aliases().nextElement();
        PrivateKey key = (PrivateKey) store.getKey(alias, password);
        Arrays.fill(password, '\0');
        X509Certificate certificate = (X509Certificate) store.getCertificate(alias);
        ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder("chaoxing-console", key,
                Collections.singletonList(certificate)).build();
        new ApkSigner.Builder(Collections.singletonList(signer)).setInputApk(new File(args[0])).setOutputApk(output)
                .setMinSdkVersion(26).setV1SigningEnabled(true).setV2SigningEnabled(true)
                .setV3SigningEnabled(true).setV4SigningEnabled(false).build().sign();
        ApkVerifier.Result result = new ApkVerifier.Builder(output).setMinCheckedPlatformVersion(26).build().verify();
        if (!result.isVerified()) throw new SecurityException("APK signature verification failed: " + result.getErrors());
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("Signature verified: v2=" + result.isVerifiedUsingV2Scheme() + ", v3=" + result.isVerifiedUsingV3Scheme());
        System.out.println("Certificate SHA-256: " + HexFormat.of().formatHex(digest.digest(certificate.getEncoded())));
        System.out.println("APK SHA-256: " + HexFormat.of().formatHex(digest.digest(Files.readAllBytes(output.toPath()))));
    }
}
