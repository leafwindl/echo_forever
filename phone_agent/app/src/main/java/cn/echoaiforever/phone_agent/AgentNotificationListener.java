package cn.echoaiforever.phone_agent;

import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONArray;
import org.json.JSONObject;

public class AgentNotificationListener extends NotificationListenerService {
    private static volatile AgentNotificationListener instance;

    public static AgentNotificationListener instance() {
        return instance;
    }

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        instance = this;
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
