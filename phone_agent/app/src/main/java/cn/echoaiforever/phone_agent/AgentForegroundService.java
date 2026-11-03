package cn.echoaiforever.phone_agent;

import android.app.Notification;
import android.app.NotificationChannel;
import android.content.pm.ServiceInfo;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import org.json.JSONObject;

public class AgentForegroundService extends Service {
    private static final String CHANNEL_ID = "echo_phone_agent";
    private static final int NOTIFICATION_ID = 2107;
    private static volatile boolean running = false;
    private static volatile String status = "未连接";
    private static volatile boolean connected = false;
    private static volatile AgentForegroundService instance;

    private final AgentWebSocketClient socket = new AgentWebSocketClient();
    private final AgentScreenCapture screenCapture = new AgentScreenCapture(this);
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private boolean reconnectScheduled;

    public static boolean isRunning() {
        return running;
    }

    public static boolean isConnected() {
        return connected;
    }

    public static String statusText() {
        return status;
    }

    public static String captureScreenshot() {
        AgentForegroundService current = instance;
        if (current != null && current.screenCapture.isReady()) {
            return current.screenCapture.captureBase64();
        }
        AgentAccessibilityService service = AgentAccessibilityService.instance();
        return service == null ? "" : service.captureScreenshotBase64();
    }

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        running = true;
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                    NOTIFICATION_ID,
                    buildNotification("正在连接 Echo 后端"),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            );
        } else {
            startForeground(NOTIFICATION_ID, buildNotification("正在连接 Echo 后端"));
        }
        if (intent != null && intent.hasExtra("projection_result_code")) {
            int resultCode = intent.getIntExtra("projection_result_code", 0);
            Intent projectionData = intent.getParcelableExtra("projection_data");
            if (projectionData != null) {
                try {
                    if (screenCapture.start(resultCode, projectionData)
                            && Build.VERSION.SDK_INT >= 29) {
                        startForeground(
                                NOTIFICATION_ID,
                                buildNotification("手机截图已授权"),
                                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
                                        | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
                        );
                    }
                } catch (Exception exc) {
                    status = "截图授权失败";
                }
            }
        }
        connectIfConfigured();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        connected = false;
        reconnectScheduled = false;
        instance = null;
        mainHandler.removeCallbacksAndMessages(null);
        socket.close();
        screenCapture.stop();
        status = "已停止";
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void connectIfConfigured() {
        String baseUrl = AgentConfig.baseUrl(this);
        String token = AgentConfig.prefs(this).getString(AgentConfig.DEVICE_TOKEN, "");
        if (token == null || token.trim().isEmpty()) {
            status = "未配对";
            connected = false;
            updateNotification();
            return;
        }
        status = "连接中";
        socket.connect(baseUrl, token, new AgentWebSocketClient.Listener() {
            @Override
            public void onOpen() {
                connected = true;
                reconnectScheduled = false;
                status = "已连接";
                updateNotification();
            }

            @Override
            public void onMessage(String text) {
                handleMessage(text);
            }

            @Override
            public void onClosed(String reason) {
                connected = false;
                status = "连接已关闭";
                updateNotification();
                scheduleReconnect();
            }

            @Override
            public void onFailure(String message) {
                connected = false;
                status = "连接失败：" + message;
                updateNotification();
                scheduleReconnect();
            }
        });
    }

    private void scheduleReconnect() {
        if (!running || reconnectScheduled) {
            return;
        }
        reconnectScheduled = true;
        mainHandler.postDelayed(() -> {
            reconnectScheduled = false;
            if (running && !connected) {
                connectIfConfigured();
            }
        }, 5000);
    }

    private void handleMessage(String text) {
        try {
            JSONObject payload = new JSONObject(text);
            String type = payload.optString("type", "");
            if ("command".equals(type)) {
                String commandId = payload.optString("command_id", "");
                String action = payload.optString("action", "");
                JSONObject arguments = payload.optJSONObject("arguments");
                if (arguments == null) {
                    arguments = new JSONObject();
                }
                JSONObject finalArguments = arguments;
                mainHandler.post(() -> executeCommand(commandId, action, finalArguments));
            }
        } catch (Exception exc) {
            status = "消息解析失败";
            updateNotification();
        }
    }

    private void executeCommand(String commandId, String action, JSONObject arguments) {
        JSONObject result = AgentCommandHandler.handle(this, action, arguments);
        JSONObject response = new JSONObject();
        try {
            response.put("type", "result");
            response.put("command_id", commandId);
            if (result.optBoolean("ok", false)) {
                response.put("data", result.optJSONObject("data"));
            } else {
                response.put("error", result.optJSONObject("error"));
            }
            socket.send(response);
            status = "已连接";
        } catch (Exception exc) {
            status = "结果回传失败";
        }
        updateNotification();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < 26) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel),
                NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription(getString(R.string.notification_text));
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(channel);
    }

    private void updateNotification() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.notify(NOTIFICATION_ID, buildNotification(status));
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                0,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.notification_title))
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_menu_compass)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .build();
    }
}
