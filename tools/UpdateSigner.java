import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.cert.CertificateFactory;
import java.util.Properties;

/** Offline signing helper. Passwords are read from an external file, never command arguments. */
public final class UpdateSigner {
    private static final byte[] DOMAIN = "KitsuneMagisk update v1\n".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        if (args.length != 4) throw new IllegalArgumentException("sign CONFIG PAYLOAD SIGNATURE | verify CERT PAYLOAD SIGNATURE");
        byte[] payload = Files.readAllBytes(Path.of(args[2]));
        if (payload.length > 131072) throw new IllegalArgumentException("Metadata too large");
        Signature signature = Signature.getInstance("SHA256withRSA");
        if (args[0].equals("sign")) {
            Properties config = new Properties();
            try (var in = new FileInputStream(args[1])) { config.load(in); }
            char[] password = config.getProperty("keyStorePass").toCharArray();
            KeyStore store = KeyStore.getInstance(new File(config.getProperty("keyStore")), password);
            PrivateKey key = (PrivateKey) store.getKey(config.getProperty("keyAlias"), config.getProperty("keyPass").toCharArray());
            signature.initSign(key);
            signature.update(DOMAIN);
            signature.update(payload);
            Files.write(Path.of(args[3]), signature.sign());
        } else if (args[0].equals("verify")) {
            try (var in = new FileInputStream(args[1])) {
                signature.initVerify(CertificateFactory.getInstance("X.509").generateCertificate(in));
            }
            signature.update(DOMAIN);
            signature.update(payload);
            if (!signature.verify(Files.readAllBytes(Path.of(args[3])))) throw new SecurityException("Invalid metadata signature");
        } else {
            throw new IllegalArgumentException("Unknown signer operation");
        }
    }
}
