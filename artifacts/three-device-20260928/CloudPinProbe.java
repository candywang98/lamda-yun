import com.company.cloudctl.companion.network.PinnedTrustManager;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManager;

/** Controller-only public TLS/health probe; no credentials or device operations. */
public class CloudPinProbe {
    private static final String HOST = "43.133.243.154.sslip.io";
    private static final String IP = "43.133.243.154";
    private static final String OLD_PIN =
        "fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1";
    private static final String NEW_PIN =
        "f2a9423e27fd8d6cdcd00d76e9da8918a402e118fe52656b84342dda6fb40725";

    private static SSLSocket connect(SSLContext context) throws Exception {
        Socket tcp = new Socket();
        try {
            tcp.connect(new InetSocketAddress(IP, 443), 10_000);
            SSLSocket tls = (SSLSocket) context.getSocketFactory()
                .createSocket(tcp, HOST, 443, true);
            tls.setSoTimeout(10_000);
            SSLParameters parameters = tls.getSSLParameters();
            parameters.setServerNames(List.of(new SNIHostName(HOST)));
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(parameters);
            tls.startHandshake();
            return tls;
        } catch (Exception failure) {
            tcp.close();
            throw failure;
        }
    }

    private static void requireRejected(String pin, String host, X509Certificate[] chain)
            throws Exception {
        try {
            new PinnedTrustManager(pin, host).checkServerTrusted(chain, "RSA");
        } catch (IllegalStateException | IllegalArgumentException expected) {
            return;
        }
        throw new IllegalStateException("Unexpected certificate acceptance");
    }

    public static void main(String[] args) throws Exception {
        X509Certificate[] chain;
        try (SSLSocket tls = connect(SSLContext.getDefault())) {
            chain = Arrays.stream(tls.getSession().getPeerCertificates())
                .map(certificate -> (X509Certificate) certificate)
                .toArray(X509Certificate[]::new);
        }
        String fingerprint = HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded())
        );
        if (!NEW_PIN.equals(fingerprint)) {
            throw new IllegalStateException("Server leaf no longer matches frozen successor");
        }
        new PinnedTrustManager(NEW_PIN, HOST).checkServerTrusted(chain, "RSA");
        new PinnedTrustManager(OLD_PIN, HOST).checkServerTrusted(chain, "RSA");
        requireRejected(OLD_PIN, "wrong.example", chain);
        requireRejected(OLD_PIN, null, chain);
        requireRejected("a".repeat(64), HOST, chain);

        SSLContext pinned = SSLContext.getInstance("TLS");
        pinned.init(null, new TrustManager[] {new PinnedTrustManager(OLD_PIN, HOST)}, null);
        try (SSLSocket tls = connect(pinned)) {
            String request = "GET /health/ready HTTP/1.1\r\nHost: " + HOST
                + "\r\nConnection: close\r\n\r\n";
            tls.getOutputStream().write(request.getBytes(StandardCharsets.US_ASCII));
            tls.getOutputStream().flush();
            String status = new BufferedReader(new InputStreamReader(
                tls.getInputStream(), StandardCharsets.US_ASCII
            )).readLine();
            if (status == null || !status.matches("HTTP/1\\.[01] 200(?: .*)?")) {
                throw new IllegalStateException("Public health read failed: " + status);
            }
            System.out.println("{\"observedAt\":\"" + Instant.now()
                + "\",\"defaultCaAndHostnameVerified\":true"
                + ",\"compiledPinnedTrustManagerVerified\":true"
                + ",\"frozenSuccessorSha256\":\"" + fingerprint
                + "\",\"negativeCases\":3,\"healthStatus\":200"
                + ",\"deviceAcceptance\":false}");
        }
    }
}
