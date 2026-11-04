package cn.echoaiforever.phone_agent;

import android.app.Notification;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class AgentNotificationListener extends NotificationListenerService {
    private static final String TAG = "EchoWechatInbound";
    private static final String WECHAT_PACKAGE = "com.tencent.mm";
    private static final String ALLOWED_CONTACT = "叶子";
    private static final long DEDUPE_WINDOW_MS = 120_000L;
    private static final Map<String, Long> RECENT = new ConcurrentHashMap<>();
    private static volatile AgentNotificationListener instance;

    public static AgentNotificationListener instance() {
        return instance;
    }

    @Override
    public void onNotificationPosted(StatusBarNotification notification) {
        handleNotification(notification, false);
    }

    private void handleNotification(StatusBarNotification notification, boolean catchup) {
        if (notification == null || !WECHAT_PACKAGE.equals(notification.getPackageName())) {
            return;
        }
        if (catchup && System.currentTimeMillis() - notification.getPostTime() > 600_000L) {
            return;
        }
        String title = text(notification, "android.title").trim();
        if (!ALLOWED_CONTACT.equals(title)) {
            return;
        }
        String content = inboundText(notification)
                .replaceFirst("^\\[\\d+条\\][^:：]*[:：]\\s*", "")
                .trim();
        if (content.isEmpty()) {
            return;
        }
        String messageId = notification.getKey() + "|" + notification.getPostTime()
                + "|" + Integer.toHexString(content.hashCode());
        long now = System.currentTimeMillis();
        Long previous = RECENT.putIfAbsent(messageId, now);
        if (previous != null && now - previous < DEDUPE_WINDOW_MS) {
            return;
        }
        RECENT.put(messageId, now);
        if (RECENT.size() > 200) {
            RECENT.entrySet().removeIf(entry -> now - entry.getValue() > DEDUPE_WINDOW_MS);
        }
        if (!AgentWechatInboundGuard.claim(content)) {
            return;
        }
        String baseUrl = AgentConfig.baseUrl(this);
        String token = AgentConfig.prefs(this).getString(AgentConfig.DEVICE_TOKEN, "");
        if (token == null || token.trim().isEmpty()) {
            return;
        }
        new Thread(
                () -> {
                    try {
                        AgentApi.sendWechatInbound(
                                baseUrl,
                                token,
                                ALLOWED_CONTACT,
                                content,
                                messageId
                        );
                    } catch (Exception exc) {
                        Log.w(TAG, "WeChat inbound upload failed", exc);
                    }
                },
                "echo-wechat-inbound"
        ).start();
    }

    private static String inboundText(StatusBarNotification notification) {
        String direct = text(notification, "android.text").trim();
        if (!direct.isEmpty()) {
            return direct;
        }
        String big = text(notification, "android.bigText").trim();
        if (!big.isEmpty()) {
            return big;
        }
        Bundle extras = notification.getNotification() == null
                ? null
                : notification.getNotification().extras;
        if (extras == null) {
            return "";
        }
        CharSequence[] lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines == null || lines.length == 0) {
            return "";
        }
        StringBuilder result = new StringBuilder();
        for (CharSequence line : lines) {
            if (line == null || line.toString().trim().isEmpty()) {
                continue;
            }
            if (result.length() > 0) {
                result.append('\n');
            }
            result.append(line.toString().trim());
        }
        return result.toString();
    }

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        instance = this;
        StatusBarNotification[] active = getActiveNotifications();
        if (active == null) {
            return;
        }
        for (StatusBarNotification notification : active) {
            handleNotification(notification, true);
        }
    }

    @Override
    public void onListenerDisconnected() {
        instance = null;
        super.onListenerDisconnected();
    }

    @Override
    public void onDestroy() {
        instance = null;
        super.onDestroy();
    }

    static JSONArray snapshot() {
        AgentNotificationListener service = instance;
        JSONArray result = new JSONArray();
        if (service == null) {
            return result;
        }
        StatusBarNotification[] notifications = service.getActiveNotifications();
        if (notifications == null) {
            return result;
        }
        for (StatusBarNotification notification : notifications) {
            if (result.length() >= 20) {
                break;
            }
            try {
                JSONObject item = new JSONObject();
                item.put("package", notification.getPackageName());
                item.put("title", text(notification, "android.title"));
                item.put("text", text(notification, "android.text"));
                item.put("time", notification.getPostTime());
                result.put(item);
            } catch (Exception ignored) {
                // Skip malformed notifications rather than breaking the whole snapshot.
            }
        }
        return result;
    }

    private static String text(StatusBarNotification notification, String key) {
        if (notification.getNotification() == null
                || notification.getNotification().extras == null) {
            return "";
        }
        CharSequence value = notification.getNotification().extras.getCharSequence(key);
        return value == null ? "" : value.toString();
    }
}
