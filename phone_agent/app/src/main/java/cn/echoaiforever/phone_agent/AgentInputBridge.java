package cn.echoaiforever.phone_agent;

import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/**
 * Sends text/keystrokes through the PC ADB bridge. The Android accessibility
 * ACTION_SET_TEXT cannot drive some React Native search fields, and adb input
 * cannot send Chinese; ADBKeyboard is the reliable bridge.
 */
final class AgentInputBridge {
    private static final String TEXT_URL = "http://127.0.0.1:8765/text";
    private static final String KEY_URL = "http://127.0.0.1:8765/key";
    private static final String URI_URL = "http://127.0.0.1:8765/open_uri";
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
            .connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(4, TimeUnit.SECONDS)
            .build();

    private AgentInputBridge() {
    }

    static boolean typeText(String text) {
        try {
            return post(TEXT_URL, new JSONObject().put("text", text));
        } catch (Exception exc) {
            return false;
        }
    }

    static boolean key(int keycode) {
        try {
            return post(KEY_URL, new JSONObject().put("keycode", keycode));
        } catch (Exception exc) {
            return false;
        }
    }

    static boolean openUri(String uri) {
        try {
            return post(URI_URL, new JSONObject().put("uri", uri));
        } catch (Exception exc) {
            return false;
        }
    }

    private static boolean post(String url, JSONObject payload) {
        try {
            Request request = new Request.Builder()
                    .url(url)
                    .post(RequestBody.create(payload.toString(), JSON))
                    .build();
            try (Response response = CLIENT.newCall(request).execute()) {
                return response.isSuccessful();
            }
        } catch (Exception exc) {
            return false;
        }
    }
}
