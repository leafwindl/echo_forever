package cn.echoaiforever.phone_agent;

import org.json.JSONObject;

import java.io.IOException;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

final class AgentApi {
    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");
    private static final OkHttpClient CLIENT = new OkHttpClient();
    private static final OkHttpClient INBOUND_CLIENT = new OkHttpClient.Builder()
            .readTimeout(180, java.util.concurrent.TimeUnit.SECONDS)
            .build();

    private AgentApi() {
    }

    static void unpair(String baseUrl, String token) throws IOException {
        Request request = new Request.Builder()
                .url(AgentConfig.normalizeBaseUrl(baseUrl) + "/mobile-agent/unpair")
                .header("Authorization", "Bearer " + token)
                .post(RequestBody.create("{}", JSON))
                .build();
        try (Response response = CLIENT.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("解除配对失败 HTTP " + response.code());
            }
        }
    }

    static void sendWechatInbound(
            String baseUrl,
            String token,
            String contact,
            String text,
            String messageId
    ) throws IOException {
        JSONObject payload = new JSONObject();
        try {
            payload.put("contact", contact);
            payload.put("text", text);
            payload.put("message_id", messageId);
        } catch (Exception exc) {
            throw new IOException("cannot build WeChat inbound payload", exc);
        }
        Request request = new Request.Builder()
                .url(AgentConfig.normalizeBaseUrl(baseUrl) + "/mobile-agent/wechat/inbound")
                .header("Authorization", "Bearer " + token)
                .post(RequestBody.create(payload.toString(), JSON))
                .build();
        try (Response response = INBOUND_CLIENT.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("微信入站 HTTP " + response.code());
            }
        }
    }

    static PairResult pair(String baseUrl, String code, String deviceName) throws IOException {
        JSONObject payload = new JSONObject();
        try {
            payload.put("code", code.trim());
            payload.put("name", deviceName.trim());
        } catch (Exception exc) {
            throw new IOException("cannot build WeChat inbound payload", exc);
        }
        Request request = new Request.Builder()
                .url(AgentConfig.normalizeBaseUrl(baseUrl) + "/mobile-agent/pair")
                .post(RequestBody.create(payload.toString(), JSON))
                .build();
        try (Response response = CLIENT.newCall(request).execute()) {
            String body = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) {
                throw new IOException("配对失败 HTTP " + response.code() + ": " + body);
            }
            JSONObject object = new JSONObject(body);
            JSONObject device = object.getJSONObject("device");
            return new PairResult(
                    device.getString("device_id"),
                    object.getString("token"),
                    device.optString("name", deviceName)
            );
        } catch (IOException exc) {
            throw exc;
        } catch (Exception exc) {
            throw new IOException("配对响应无法解析", exc);
        }
    }

    static final class PairResult {
        final String deviceId;
        final String token;
        final String name;

        PairResult(String deviceId, String token, String name) {
            this.deviceId = deviceId;
            this.token = token;
            this.name = name;
        }
    }
}
