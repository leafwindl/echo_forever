package cn.echoaiforever.phone_agent;

import android.content.Context;
import android.content.SharedPreferences;

final class AgentConfig {
    static final String PREFS = "phone_agent";
    static final String BASE_URL = "base_url";
    static final String PAIRING_CODE = "pairing_code";
    static final String DEVICE_NAME = "device_name";
    static final String DEVICE_TOKEN = "device_token";
    static final String DEVICE_ID = "device_id";
    static final String DEFAULT_BASE_URL = "https://api.echoaiforever.cn";

    private AgentConfig() {
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String baseUrl(Context context) {
        String value = prefs(context).getString(BASE_URL, DEFAULT_BASE_URL);
        return value == null ? DEFAULT_BASE_URL : value.trim();
    }

    static String normalizeBaseUrl(String value) {
        String trimmed = value == null ? "" : value.trim();
        if (trimmed.isEmpty()) {
            return DEFAULT_BASE_URL;
        }
        if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
            trimmed = "https://" + trimmed;
        }
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }

    static String websocketUrl(String baseUrl) {
        String normalized = normalizeBaseUrl(baseUrl);
        if (normalized.startsWith("https://")) {
            return "wss://" + normalized.substring("https://".length()) + "/mobile-agent/ws";
        }
        return "ws://" + normalized.substring("http://".length()) + "/mobile-agent/ws";
    }
}
