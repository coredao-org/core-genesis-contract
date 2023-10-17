import java.io.*;

public class SolidityCommentCropper {
    private static final String PRODUCT_COMMENT_START = "@product";

    private static final String[] filesToCrop = {
            "ValidatorSet.template",
            "System.template",
            "SlashIndicator.template",
            "PledgeAgent.template",
            "GovHub.template",
            "CandidateHub.template",
            "BtcLightClient.template",
            "SystemReward.sol",
            "System.sol",
            "RelayerHub.sol",
            "Foundation.sol",
            "Burn.sol",
    };

    static int commentCtr;

    public static void main(String[] args) {
        commentCtr = 0;
        final String _BASE = "../"; //core-genesis-contract/
        final String _PATH = _BASE + "contracts/";
        if (!new File(_PATH).exists()) {
          throw new RuntimeException("bad path: " + _PATH);
        }

        BufferedWriter writer = prepOutputFile(_BASE + "comment-crop/all-comments.txt");
        for (String file : filesToCrop) {
            parseFileForComments(_PATH + file, writer);
        }

        try {
            writer.flush();
            writer.close();
        } catch (IOException e) {
            throw new RuntimeException(e);
        }

        System.out.println("Total of " + commentCtr + " comments");
    }

    private static BufferedWriter prepOutputFile(String outFilePath) {
        File f = new File(outFilePath);
        f.mkdirs();
        if (f.exists()) {
            f.delete();
        }
        try {
            f.createNewFile();
        } catch (IOException e) {
            throw new RuntimeException("failed to create out file " + outFilePath + ": " + e);
        }
        BufferedWriter writer;
        try {
            writer = new BufferedWriter(new FileWriter(f, false));
        } catch (IOException e) {
            throw new RuntimeException("failed to create out file writer " + outFilePath + ": " + e);
        }
        return writer;
    }

    public static void parseFileForComments(String filePath, BufferedWriter outFileWriter) {
        File f = new File(filePath);
        if (!f.exists()) {
            throw new RuntimeException("missing file: " + f);
        }
        BufferedReader reader;
        boolean inComment = false;
        try {
            reader = new BufferedReader(new FileReader(f.getAbsolutePath()));
            String line = reader.readLine();
            while (line != null) {
                if (line.contains(PRODUCT_COMMENT_START)) {
                    commentCtr++;
                    writeLine(outFileWriter, line);
                    inComment = true;
                } else if (inComment) {
                    writeLine(outFileWriter, line);
                    boolean endOfComment = line.contains("{");
                    if (endOfComment) {
                        writeLine(outFileWriter,"");
                        writeLine(outFileWriter,"");
                        inComment = false;
                    }
                }

                line = reader.readLine(); // next line
            }
            reader.close();
        } catch (IOException e) {
            throw new RuntimeException("error parsing file: " + f + ": " + e);
        }
    }

    private static void writeLine(BufferedWriter outFileWriter, String line)  {
        try {
            outFileWriter.write(line);
            outFileWriter.newLine();
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }
}
