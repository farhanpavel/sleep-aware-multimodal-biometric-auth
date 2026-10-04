import com.machinezoo.sourceafis.*;
import java.nio.file.*;

public class FingerprintMatcher {
    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.out.println("Usage: java FingerprintMatcher <mode> <img1> <img2>");
            System.exit(1);
        }

        String mode     = args[0];
        String img1Path = args[1];
        String img2Path = args[2];

        if (mode.equals("match")) {
            byte[] enrolledBytes = Files.readAllBytes(Paths.get(img1Path));
            byte[] probeBytes    = Files.readAllBytes(Paths.get(img2Path));

            FingerprintImageOptions options = new FingerprintImageOptions()
                .dpi(500);

            FingerprintTemplate enrolled = new FingerprintTemplate(
                new FingerprintImage(enrolledBytes, options)
            );

            FingerprintTemplate probe = new FingerprintTemplate(
                new FingerprintImage(probeBytes, options)
            );

            double score = new com.machinezoo.sourceafis.FingerprintMatcher(enrolled)
                .match(probe);

            System.out.println(score);
        }
    }
}