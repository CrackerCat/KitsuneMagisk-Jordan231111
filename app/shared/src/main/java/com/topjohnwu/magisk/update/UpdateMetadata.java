package com.topjohnwu.magisk.update;

import android.os.Build;
import android.util.Base64;
import android.util.JsonReader;
import android.util.JsonToken;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** The same signed update contract is used by the full manager and the clean stub. */
public final class UpdateMetadata {
    public static final int MAX_METADATA = 131072;
    public static final long MAX_APK = 200L * 1024 * 1024;
    public static final long MAX_VALIDITY = 30L * 24 * 60 * 60;
    public static final long CLOCK_SKEW = 300;
    public static final byte[] DOMAIN = "KitsuneMagisk update v1\n".getBytes(StandardCharsets.UTF_8);

    public final String envelope;
    public final String payloadHash;
    public final String channel;
    public final long sequence;
    public final long issuedAt;
    public final long expiresAt;
    public final int versionCode;
    public final int minSdk;
    public final String versionName;
    public final String notes;
    public final Artifact manager;
    public final Artifact stub;
    public final Map<String, Object> fields;

    public static final class Artifact {
        public final String url;
        public final long size;
        public final String sha256;

        private Artifact(Map<String, Object> map, long maximum) throws IOException {
            keys(map, "url", "size", "sha256");
            url = string(map, "url", 2048);
            size = number(map, "size", 1, maximum);
            sha256 = hex(map, "sha256", 64);
        }
    }

    private UpdateMetadata(String envelope, byte[] payload, Map<String, Object> map) throws IOException {
        keys(map, "schema", "channel", "build_channel", "sequence", "issued_at", "expires_at", "application_id",
                "product_version", "app_version_code", "version_name", "source_commit", "source_digest",
                "source_dirty", "upstream_version", "upstream_commit", "build_id", "protocol_version",
                "variant", "certificate_sha256", "manager", "stub", "release_notes", "tag", "min_sdk");
        number(map, "schema", 1, 1);
        this.envelope = envelope;
        payloadHash = sha256(payload);
        fields = java.util.Collections.unmodifiableMap(map);
        channel = string(map, "channel", 16);
        token(map, "build_channel");
        if (!Arrays.asList("stable", "beta", "canary").contains(channel))
            throw new IOException("Unsupported update channel");
        sequence = number(map, "sequence", 1, Long.MAX_VALUE);
        issuedAt = number(map, "issued_at", 1, Long.MAX_VALUE - MAX_VALIDITY);
        expiresAt = number(map, "expires_at", issuedAt + 1, issuedAt + MAX_VALIDITY);
        versionCode = (int) number(map, "app_version_code", 31001, 2100000000);
        minSdk = (int) number(map, "min_sdk", 1, 10000);
        number(map, "protocol_version", 1, Integer.MAX_VALUE);
        versionName = token(map, "version_name");
        token(map, "product_version");
        token(map, "upstream_version");
        token(map, "application_id");
        String tag = token(map, "tag");
        if (!tag.startsWith("kitsune-")) throw new IOException("Not a Kitsune release tag");
        if (!"release".equals(string(map, "variant", 16)))
            throw new IOException("Public updates require a release artifact");
        if (!(map.get("source_dirty") instanceof Boolean)) throw new IOException("Invalid source state");
        hex(map, "source_commit", 40);
        hex(map, "upstream_commit", 40);
        hex(map, "source_digest", 64);
        hex(map, "build_id", 64);
        hex(map, "certificate_sha256", 64);
        notes = string(map, "release_notes", 32768);
        manager = new Artifact(object(map, "manager"), MAX_APK);
        stub = new Artifact(object(map, "stub"), 8 * 1024 * 1024);
    }

    public static UpdateMetadata verify(String envelope, byte[] certificate, String expectedChannel,
                                        String applicationId, long now, int minimumCode)
            throws IOException {
        try {
            Map<String, Object> outer = parse(envelope);
            keys(outer, "schema", "key_id", "payload", "signature");
            number(outer, "schema", 1, 1);
            if (!sha256(certificate).equals(hex(outer, "key_id", 64)))
                throw new IOException("Unknown update signing key");
            byte[] payload = base64(string(outer, "payload", MAX_METADATA));
            byte[] signature = base64(string(outer, "signature", 1024));
            X509Certificate cert = (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(new ByteArrayInputStream(certificate));
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(cert.getPublicKey());
            verifier.update(DOMAIN);
            verifier.update(payload);
            if (!verifier.verify(signature)) throw new IOException("Invalid update signature");
            UpdateMetadata metadata = new UpdateMetadata(envelope, payload, parse(utf8(payload)));
            if (!metadata.channel.equals(expectedChannel)) throw new IOException("Wrong update channel");
            if (!applicationId.equals(metadata.fields.get("application_id")))
                throw new IOException("Wrong update package");
            if (!sha256(certificate).equals(metadata.fields.get("certificate_sha256")))
                throw new IOException("Wrong update certificate");
            metadata.checkTime(now);
            if (metadata.minSdk > Build.VERSION.SDK_INT)
                throw new IOException("Update requires a newer Android version");
            if (metadata.versionCode < minimumCode) throw new IOException("Update would downgrade the manager");
            return metadata;
        } catch (GeneralSecurityException | IllegalArgumentException e) {
            throw new IOException("Invalid signed update", e);
        }
    }

    public void checkTime(long now) throws IOException {
        if (issuedAt > now + CLOCK_SKEW || expiresAt <= now)
            throw new IOException("Update metadata expired or device clock is incorrect");
    }

    public static String sha256(byte[] bytes) throws IOException {
        try {
            return toHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (GeneralSecurityException e) {
            throw new IOException(e);
        }
    }

    public static String toHex(byte[] bytes) {
        char[] alphabet = "0123456789abcdef".toCharArray();
        char[] result = new char[bytes.length * 2];
        for (int i = 0; i < bytes.length; ++i) {
            result[i * 2] = alphabet[(bytes[i] & 255) >>> 4];
            result[i * 2 + 1] = alphabet[bytes[i] & 15];
        }
        return new String(result);
    }

    private static byte[] base64(String value) throws IOException {
        byte[] bytes = Base64.decode(value, Base64.NO_WRAP);
        if (!Base64.encodeToString(bytes, Base64.NO_WRAP).equals(value))
            throw new IOException("Noncanonical base64");
        return bytes;
    }

    public static String utf8(byte[] bytes) throws IOException {
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static Map<String, Object> parse(String json) throws IOException {
        if (json.length() > MAX_METADATA) throw new IOException("Update metadata is too large");
        try (JsonReader reader = new JsonReader(new StringReader(json))) {
            reader.setLenient(false);
            Map<String, Object> result = readObject(reader, 0);
            if (reader.peek() != JsonToken.END_DOCUMENT) throw new IOException("Trailing JSON data");
            return result;
        } catch (IllegalStateException | NumberFormatException e) {
            throw new IOException("Malformed update metadata", e);
        }
    }

    private static Map<String, Object> readObject(JsonReader reader, int depth) throws IOException {
        if (depth > 3) throw new IOException("Update metadata is too deeply nested");
        Map<String, Object> result = new HashMap<>();
        reader.beginObject();
        while (reader.hasNext()) {
            String name = reader.nextName();
            if (result.containsKey(name) || result.size() >= 32) throw new IOException("Duplicate or excessive JSON fields");
            Object value;
            switch (reader.peek()) {
                case STRING -> value = reader.nextString();
                case NUMBER -> {
                    String number = reader.nextString();
                    if (!number.matches("0|[1-9][0-9]*")) throw new IOException("Expected an unsigned integer");
                    value = Long.parseLong(number);
                }
                case BOOLEAN -> value = reader.nextBoolean();
                case BEGIN_OBJECT -> value = readObject(reader, depth + 1);
                default -> throw new IOException("Unsupported JSON value");
            }
            result.put(name, value);
        }
        reader.endObject();
        return result;
    }

    public static void keys(Map<String, Object> map, String... names) throws IOException {
        if (!map.keySet().equals(new HashSet<>(Arrays.asList(names))))
            throw new IOException("Missing or unknown update fields");
    }

    public static String string(Map<String, Object> map, String key, int limit) throws IOException {
        Object value = map.get(key);
        if (!(value instanceof String) || ((String) value).isEmpty() || ((String) value).length() > limit)
            throw new IOException("Invalid update field: " + key);
        return (String) value;
    }

    public static String token(Map<String, Object> map, String key) throws IOException {
        String value = string(map, key, 128);
        if (!value.matches("[a-zA-Z0-9][a-zA-Z0-9._-]*")) throw new IOException("Invalid update identifier");
        return value;
    }

    public static long number(Map<String, Object> map, String key, long min, long max) throws IOException {
        Object value = map.get(key);
        if (!(value instanceof Long) || (Long) value < min || (Long) value > max)
            throw new IOException("Invalid update number: " + key);
        return (Long) value;
    }

    public static String hex(Map<String, Object> map, String key, int length) throws IOException {
        String value = string(map, key, length);
        if (!value.matches("[0-9a-f]{" + length + "}")) throw new IOException("Invalid update digest");
        return value;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> object(Map<String, Object> map, String key) throws IOException {
        Object value = map.get(key);
        if (!(value instanceof Map)) throw new IOException("Invalid update object: " + key);
        return (Map<String, Object>) value;
    }
}
