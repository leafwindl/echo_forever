package cn.echoaiforever.phone_agent;

import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * Development-only bridge for phones where the OEM blocks MediaProjection.
 * The PC runs scripts/adb_screenshot_bridge.py and sets up adb reverse.
 */
final class AgentScreenshotBridge {
    static final String DEFAULT_URL = "http://127.0.0.1:8765/screenshot";

    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
            .connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(4, TimeUnit.SECONDS)
            .build();

    private AgentScreenshotBridge() {
    }

    static JSONObject capture() {
        Request request = new Request.Builder()
                .url(DEFAULT_URL)
                .get()
                .build();
        try (Response response = CLIENT.newCall(request).execute()) {
            if (!response.isSuccessful() || response.body() == null) {
                return null;
            }
            JSONObject body = new JSONObject(response.body().string());
            if (body.optString("image_base64", "").isEmpty()) {
                return null;
            }
            return body;
        } catch (Exception exc) {
            return null;
        }
    }
}
