package cn.echoaiforever.phone_agent;

import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

final class AgentWebSocketClient {
    interface Listener {
        void onOpen();

        void onMessage(String text);

        void onClosed(String reason);

        void onFailure(String message);
    }

    private final OkHttpClient client = new OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .pingInterval(20, TimeUnit.SECONDS)
            .build();
    private volatile WebSocket socket;
    private volatile boolean connected;

    boolean isConnected() {
        return connected && socket != null;
    }

    void connect(String baseUrl, String token, Listener listener) {
        close();
        Request request = new Request.Builder()
                .url(AgentConfig.websocketUrl(baseUrl))
                .header("Authorization", "Bearer " + token)
                .build();
        socket = client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                connected = true;
                listener.onOpen();
                try {
                    webSocket.send(new JSONObject().put("type", "hello").toString());
                } catch (Exception ignored) {
                    // Hello is optional; the server already authenticated the socket.
                }
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                listener.onMessage(text);
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                connected = false;
                listener.onClosed(reason);
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                connected = false;
                listener.onFailure(t.getMessage() == null ? t.toString() : t.getMessage());
            }
        });
    }

    boolean send(JSONObject payload) {
        WebSocket current = socket;
        return current != null && current.send(payload.toString());
    }

    void close() {
        connected = false;
        WebSocket current = socket;
        socket = null;
        if (current != null) {
            current.close(1000, "client stopped");
        }
    }
}
