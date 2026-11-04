package cn.echoaiforever.phone_agent;

import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class AgentWechatInboundGuard {
    private static final long DEDUPE_WINDOW_MS = 8_000L;
    private static final Map<String, Long> RECENT = new ConcurrentHashMap<>();

    private AgentWechatInboundGuard() {
    }

    static boolean claim(String text) {
        String normalized = normalize(text);
        if (normalized.isEmpty()) {
            return false;
        }
        long now = System.currentTimeMillis();
        Long previous = RECENT.putIfAbsent(normalized, now);
        if (previous != null && now - previous < DEDUPE_WINDOW_MS) {
            return false;
        }
        RECENT.put(normalized, now);
        if (RECENT.size() > 200) {
            RECENT.entrySet().removeIf(
                    entry -> now - entry.getValue() > DEDUPE_WINDOW_MS
            );
        }
        return true;
    }

    private static String normalize(String text) {
        if (text == null) {
            return "";
        }
        return text.replace('\n', ' ')
                .replaceAll("\\s+", "")
                .toLowerCase(Locale.ROOT)
                .trim();
    }
}
