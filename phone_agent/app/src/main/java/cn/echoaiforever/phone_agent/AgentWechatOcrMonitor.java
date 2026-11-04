package cn.echoaiforever.phone_agent;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Rect;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

final class AgentWechatOcrMonitor {
    private static final String TAG = "EchoWechatOcr";
    private static final String WECHAT_PACKAGE = "com.tencent.mm";
    private static final String CONTACT = "叶子";
    private static final long POLL_INTERVAL_MS = 2500L;
    private static final long OUTBOUND_SUPPRESSION_MS = 120_000L;
    private static final Map<String, Long> RECENT_OUTBOUND = new ConcurrentHashMap<>();

    private final AgentForegroundService service;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final TextRecognizer recognizer = TextRecognition.getClient(
            new ChineseTextRecognizerOptions.Builder().build()
    );
    private final AtomicBoolean inFlight = new AtomicBoolean(false);
    private volatile boolean started;
    private boolean primed;
    private List<String> lastIncoming = new ArrayList<>();

    AgentWechatOcrMonitor(AgentForegroundService service) {
        this.service = service;
    }

    static void rememberOutbound(String text) {
        String normalized = normalizeStatic(text);
        if (normalized.isEmpty()) {
            return;
        }
        long now = System.currentTimeMillis();
        RECENT_OUTBOUND.put(normalized, now);
        RECENT_OUTBOUND.entrySet().removeIf(
                entry -> now - entry.getValue() > OUTBOUND_SUPPRESSION_MS
        );
    }

    private static boolean isRecentOutbound(String text) {
        String normalized = normalizeStatic(text);
        if (normalized.isEmpty()) {
            return false;
        }
        long now = System.currentTimeMillis();
        Long sentAt = RECENT_OUTBOUND.get(normalized);
        return sentAt != null && now - sentAt <= OUTBOUND_SUPPRESSION_MS;
    }

    private static String normalizeStatic(String value) {
        if (value == null) {
            return "";
        }
        return value.replace('\n', ' ')
                .replaceAll("\\s+", "")
                .toLowerCase(Locale.ROOT)
                .trim();
    }

    void start() {
        if (started) {
            return;
        }
        if (!AgentConfig.wechatForegroundOcrEnabled(service)) {
            Log.i(TAG, "not started: preference disabled");
            return;
        }
        Log.i(TAG, "started");
        started = true;
        mainHandler.postDelayed(this::tick, 1200L);
    }

    void stop() {
        started = false;
        mainHandler.removeCallbacksAndMessages(null);
        recognizer.close();
    }

    private void tick() {
        if (!started) {
            return;
        }
        mainHandler.postDelayed(this::tick, POLL_INTERVAL_MS);
        if (inFlight.get()) {
            return;
        }
        AgentAccessibilityService accessibility = AgentAccessibilityService.instance();
        if (accessibility == null
                || !WECHAT_PACKAGE.equals(accessibility.currentPackage())) {
            resetChat();
            return;
        }
        inFlight.set(true);
        new Thread(this::captureAndRecognize, "echo-wechat-ocr").start();
    }

    private void captureAndRecognize() {
        JSONObject shot = AgentScreenshotBridge.capture();
        if (shot == null) {
            inFlight.set(false);
            return;
        }
        String encoded = shot.optString("image_base64", "");
        if (encoded.isEmpty()) {
            inFlight.set(false);
            return;
        }
        final Bitmap bitmap;
        try {
            byte[] bytes = Base64.decode(encoded, Base64.DEFAULT);
            bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        } catch (Exception exc) {
            Log.w(TAG, "screenshot decode failed", exc);
            inFlight.set(false);
            return;
        }
        if (bitmap == null) {
            inFlight.set(false);
            return;
        }
        InputImage image = InputImage.fromBitmap(bitmap, 0);
        recognizer.process(image)
                .addOnSuccessListener(result -> {
                    try {
                        handleResult(result, bitmap);
                    } finally {
                        bitmap.recycle();
                        inFlight.set(false);
                    }
                })
                .addOnFailureListener(exc -> {
                    Log.w(TAG, "OCR failed", exc);
                    bitmap.recycle();
                    inFlight.set(false);
                });
    }

    private void handleResult(Text result, Bitmap bitmap) {
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        List<IncomingLine> incoming = new ArrayList<>();
        boolean contactVisible = false;
        for (Text.TextBlock block : result.getTextBlocks()) {
            Rect bounds = block.getBoundingBox();
            if (bounds == null) {
                continue;
            }
            String content = normalize(block.getText());
            if (content.isEmpty()) {
                continue;
            }
            if (bounds.top < height * 0.18 && CONTACT.equals(content)) {
                contactVisible = true;
            }
            if (!isIncomingMessage(content, bounds, bitmap, width, height)) {
                continue;
            }
            incoming.add(new IncomingLine(content, bounds.top));
        }
        if (!contactVisible) {
            Log.i(TAG, "contact not visible; resetting");
            resetChat();
            return;
        }
        incoming.sort(Comparator.comparingInt(item -> item.top));
        List<String> texts = new ArrayList<>();
        for (IncomingLine line : incoming) {
            texts.add(line.text);
        }
        if (!primed) {
            lastIncoming = texts;
            primed = true;
            Log.i(TAG, "primed incoming=" + texts.size());
            return;
        }
        if (texts.equals(lastIncoming)) {
            return;
        }
        List<String> additions = new ArrayList<>();
        if (texts.size() > lastIncoming.size()
                && texts.subList(0, lastIncoming.size()).equals(lastIncoming)) {
            additions.addAll(texts.subList(lastIncoming.size(), texts.size()));
        } else if (!texts.isEmpty()) {
            String last = texts.get(texts.size() - 1);
            String previous = lastIncoming.isEmpty()
                    ? ""
                    : lastIncoming.get(lastIncoming.size() - 1);
            if (!last.equals(previous) && incoming.get(incoming.size() - 1).top > height * 0.35) {
                additions.add(last);
            }
        }
        lastIncoming = texts;
        Log.i(TAG, "incoming=" + texts.size() + " additions=" + additions.size());
        for (String text : additions) {
            upload(text);
        }
    }

    private boolean isIncomingMessage(
            String content,
            Rect bounds,
            Bitmap bitmap,
            int width,
            int height
    ) {
        if (bounds.top < height * 0.12 || bounds.bottom > height * 0.91) {
            return false;
        }
        if (bounds.left >= width * 0.55 || bounds.right >= width * 0.9) {
            return false;
        }
        if (content.equals(CONTACT) || content.equals("微信") || content.equals("发送")) {
            return false;
        }
        if (!isUserWhiteBubble(bitmap, bounds)) {
            return false;
        }
        if (isOutgoingGreen(bitmap, bounds)) {
            return false;
        }
        if (isRecentOutbound(content)) {
            return false;
        }
        if (content.matches("\\d{1,2}:\\d{2}")
                || content.matches("\\d{4}-\\d{1,2}-\\d{1,2}.*")
                || content.contains("以上是打招呼的消息")
                || content.contains("对方正在输入")
                || content.contains("按住 说话")
                || content.contains("按住 转文字")
                || content.contains("关闭无障碍")
                || content.contains("保持开启")
                || content.contains("检测到")
                || content.equals("返回")
                || content.equals("更多")) {
            return false;
        }
        return true;
    }

    private boolean isUserWhiteBubble(Bitmap bitmap, Rect bounds) {
        int left = Math.max(0, bounds.left - 28);
        int right = Math.min(bitmap.getWidth() - 1, bounds.right + 28);
        int top = Math.max(0, bounds.top - 14);
        int bottom = Math.min(bitmap.getHeight() - 1, bounds.bottom + 14);
        int green = 0;
        int light = 0;
        for (int y = top; y <= bottom; y += 10) {
            for (int x = left; x <= right; x += 10) {
                int color = bitmap.getPixel(x, y);
                int red = Color.red(color);
                int greenChannel = Color.green(color);
                int blue = Color.blue(color);
                if (greenChannel > red + 18 && greenChannel > blue + 18) {
                    green++;
                } else if (red > 180 && greenChannel > 180 && blue > 180) {
                    light++;
                }
            }
        }
        return green == 0 && light >= 5;
    }

    private boolean isOutgoingGreen(Bitmap bitmap, Rect bounds) {
        int left = Math.max(0, bounds.left - 28);
        int right = Math.min(bitmap.getWidth() - 1, bounds.right + 28);
        int top = Math.max(0, bounds.top - 14);
        int bottom = Math.min(bitmap.getHeight() - 1, bounds.bottom + 14);
        int green = 0;
        int scanned = 0;
        for (int y = top; y <= bottom; y += 10) {
            for (int x = left; x <= right; x += 10) {
                int color = bitmap.getPixel(x, y);
                int red = Color.red(color);
                int greenChannel = Color.green(color);
                int blue = Color.blue(color);
                scanned++;
                if (greenChannel > red + 18 && greenChannel > blue + 18) {
                    green++;
                }
            }
        }
        return scanned > 0 && green >= 1;
    }

    private String normalize(String value) {
        if (value == null) {
            return "";
        }
        return value.replace('\n', ' ').replaceAll("\\s+", " ").trim();
    }

    private void resetChat() {
        primed = false;
        lastIncoming = new ArrayList<>();
    }

    private void upload(String text) {
        Log.i(TAG, "upload candidate=" + text);
        if (!AgentWechatInboundGuard.claim(text)) {
            return;
        }
        String token = AgentConfig.prefs(service).getString(AgentConfig.DEVICE_TOKEN, "");
        if (token == null || token.trim().isEmpty()) {
            return;
        }
        String baseUrl = AgentConfig.baseUrl(service);
        String messageId = "ocr|" + System.currentTimeMillis() + "|"
                + Integer.toHexString(text.hashCode());
        new Thread(
                () -> {
                    try {
                        AgentApi.sendWechatInbound(
                                baseUrl,
                                token,
                                CONTACT,
                                text,
                                messageId
                        );
                    } catch (Exception exc) {
                        Log.w(TAG, "OCR message upload failed", exc);
                    }
                },
                "echo-wechat-ocr-upload"
        ).start();
    }

    private static final class IncomingLine {
        final String text;
        final int top;

        IncomingLine(String text, int top) {
            this.text = text;
            this.top = top;
        }
    }
}
