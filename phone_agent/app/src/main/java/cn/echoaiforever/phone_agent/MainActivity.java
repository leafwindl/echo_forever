package cn.echoaiforever.phone_agent;

import android.Manifest;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private TextView statusView;
    private TextView detailView;
    private EditText serverUrl;
    private EditText pairingCode;
    private EditText deviceName;
    private Button wechatOcrToggle;
    private SharedPreferences preferences;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = AgentConfig.prefs(this);
        setContentView(buildContentView());
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 11);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshStatus();
    }

    private View buildContentView() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(24), dp(24), dp(24), dp(32));
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("Echo Phone Agent");
        title.setTextSize(28);
        title.setTextColor(Color.rgb(38, 35, 49));
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("安卓手机执行端 · B 阶段骨架");
        subtitle.setTextSize(14);
        subtitle.setTextColor(Color.rgb(111, 106, 120));
        subtitle.setPadding(0, dp(4), 0, dp(20));
        root.addView(subtitle);

        statusView = new TextView(this);
        statusView.setTextSize(18);
        statusView.setPadding(dp(16), dp(14), dp(16), dp(14));
        statusView.setBackgroundColor(Color.rgb(243, 240, 248));
        root.addView(statusView);

        detailView = new TextView(this);
        detailView.setTextSize(12);
        detailView.setTextColor(Color.rgb(111, 106, 120));
        detailView.setPadding(0, dp(8), 0, dp(16));
        root.addView(detailView);

        root.addView(button("打开无障碍设置", v -> openAccessibilitySettings()));
        root.addView(button("刷新状态", v -> refreshStatus()));
        root.addView(button("启动前台服务", v -> startAgentService()));
        root.addView(button("停止前台服务", v -> stopAgentService()));
        root.addView(button("读取当前界面", v -> readCurrentUi()));
        root.addView(button("回到桌面", v -> goHome()));
        root.addView(button("打开通知读取设置", v -> openNotificationSettings()));
        wechatOcrToggle = button("", v -> toggleWechatOcr());
        root.addView(wechatOcrToggle);
        root.addView(button("解除本机配对", v -> unpair()));

        TextView serverLabel = new TextView(this);
        serverLabel.setText("后端地址（本地测试可用 http://127.0.0.1:8000）");
        serverLabel.setTextSize(13);
        serverLabel.setPadding(0, dp(20), 0, dp(6));
        root.addView(serverLabel);

        serverUrl = new EditText(this);
        serverUrl.setSingleLine(true);
        serverUrl.setText(preferences.getString(
                AgentConfig.BASE_URL,
                AgentConfig.DEFAULT_BASE_URL
        ));
        root.addView(serverUrl);

        TextView codeLabel = new TextView(this);
        codeLabel.setText("配对码（在 Echo 后端生成）");
        codeLabel.setTextSize(13);
        codeLabel.setPadding(0, dp(12), 0, dp(6));
        root.addView(codeLabel);

        pairingCode = new EditText(this);
        pairingCode.setSingleLine(true);
        pairingCode.setHint("例如 ABCD2345");
        pairingCode.setText(preferences.getString(AgentConfig.PAIRING_CODE, ""));
        root.addView(pairingCode);

        deviceName = new EditText(this);
        deviceName.setSingleLine(true);
        deviceName.setHint("设备名称");
        deviceName.setText(preferences.getString(
                AgentConfig.DEVICE_NAME,
                "Echo 的手机"
        ));
        root.addView(deviceName);

        root.addView(button("配对并连接", v -> pairAndConnect()));

        TextView boundary = new TextView(this);
        boundary.setText(
                "边界：仅用于专用测试手机。无障碍服务可读取屏幕内容；"
                        + "配对、截图授权、网络协议和安全确认将在后续 B 阶段接入。"
        );
        boundary.setTextSize(12);
        boundary.setTextColor(Color.rgb(140, 120, 80));
        boundary.setPadding(0, dp(18), 0, 0);
        root.addView(boundary);
        return scroll;
    }

    private Button button(String text, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(text);
        button.setOnClickListener(listener);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.topMargin = dp(8);
        button.setLayoutParams(params);
        return button;
    }

    private void toggleWechatOcr() {
        boolean enabled = !AgentConfig.wechatForegroundOcrEnabled(this);
        preferences.edit().putBoolean(AgentConfig.WECHAT_FOREGROUND_OCR, enabled).apply();
        AgentForegroundService.refreshWechatOcr();
        refreshStatus();
        Toast.makeText(
                this,
                enabled ? "微信前台 OCR 已開啟" : "微信前台 OCR 已關閉",
                Toast.LENGTH_SHORT
        ).show();
    }

    private void refreshStatus() {
        boolean connected = AgentAccessibilityService.instance() != null;
        boolean enabled = isAccessibilityEnabled();
        statusView.setText(connected ? "无障碍服务：已连接" : "无障碍服务：未连接");
        statusView.setTextColor(
                connected ? Color.rgb(32, 120, 72) : Color.rgb(160, 70, 50)
        );
        if (wechatOcrToggle != null) {
            wechatOcrToggle.setText(
                    "微信前台 OCR：" + (
                            AgentConfig.wechatForegroundOcrEnabled(this)
                                    ? "已開啟"
                                    : "已關閉"
                    )
            );
        }
        String deviceId = preferences.getString(AgentConfig.DEVICE_ID, "");
        detailView.setText(
                "系统开关：" + (enabled ? "已开启" : "未开启")
                        + "\n应用包名：" + getPackageName()
                        + "\n前台服务：" + (AgentForegroundService.isRunning() ? "运行中" : "未运行")
                        + "\n后端连接：" + (AgentForegroundService.isConnected() ? "已连接" : "未连接")
                        + "\n连接状态：" + AgentForegroundService.statusText()
                        + "\n设备：" + (deviceId.isEmpty() ? "尚未配对" : deviceId)
                        + "\n通知读取：" + (isNotificationListenerEnabled() ? "已开启" : "未开启")
        );
    }

    private boolean isNotificationListenerEnabled() {
        String enabled = Settings.Secure.getString(
                getContentResolver(),
                "enabled_notification_listeners"
        );
        ComponentName component = new ComponentName(this, AgentNotificationListener.class);
        return enabled != null && enabled.contains(component.flattenToString());
    }

    private boolean isAccessibilityEnabled() {
        String enabled = Settings.Secure.getString(
                getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        );
        return enabled != null && enabled.contains(
                getPackageName() + "/" + AgentAccessibilityService.class.getName()
        );
    }

    private void openAccessibilitySettings() {
        startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
    }

    private void openNotificationSettings() {
        startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
    }

    private void startAgentService() {
        Intent intent = new Intent(this, AgentForegroundService.class);
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
        Toast.makeText(this, "前台服务启动请求已发送", Toast.LENGTH_SHORT).show();
        refreshStatus();
    }

    private void stopAgentService() {
        stopService(new Intent(this, AgentForegroundService.class));
        refreshStatus();
    }

    private void unpair() {
        String baseUrl = AgentConfig.baseUrl(this);
        String token = preferences.getString(AgentConfig.DEVICE_TOKEN, "");
        preferences.edit()
                .remove(AgentConfig.DEVICE_TOKEN)
                .remove(AgentConfig.DEVICE_ID)
                .apply();
        stopService(new Intent(this, AgentForegroundService.class));
        pairingCode.setText("");
        refreshStatus();
        if (!token.isEmpty()) {
            new Thread(() -> {
                try {
                    AgentApi.unpair(baseUrl, token);
                } catch (Exception ignored) {
                    // Local unpair is what matters on the phone; server revocation is best effort.
                }
            }, "phone-agent-unpair").start();
        }
        Toast.makeText(this, "本机配对信息已清除", Toast.LENGTH_SHORT).show();
    }

    private void readCurrentUi() {
        AgentAccessibilityService service = AgentAccessibilityService.instance();
        if (service == null) {
            Toast.makeText(this, "无障碍服务未连接，请先开启", Toast.LENGTH_SHORT).show();
            return;
        }
        detailView.setText(service.dumpTree());
    }

    private void goHome() {
        AgentAccessibilityService service = AgentAccessibilityService.instance();
        if (service == null) {
            Toast.makeText(this, "无障碍服务未连接，请先开启", Toast.LENGTH_SHORT).show();
            return;
        }
        service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME);
    }

    private void pairAndConnect() {
        final String baseUrl = AgentConfig.normalizeBaseUrl(
                serverUrl.getText().toString()
        );
        final String code = pairingCode.getText().toString().trim().toUpperCase();
        final String name = deviceName.getText().toString().trim();
        if (code.isEmpty()) {
            Toast.makeText(this, "先填写后端生成的配对码", Toast.LENGTH_SHORT).show();
            return;
        }
        preferences.edit()
                .putString(AgentConfig.BASE_URL, baseUrl)
                .putString(AgentConfig.PAIRING_CODE, code)
                .putString(AgentConfig.DEVICE_NAME, name)
                .apply();
        detailView.setText("正在配对：" + baseUrl);
        new Thread(() -> {
            try {
                AgentApi.PairResult result = AgentApi.pair(baseUrl, code, name);
                preferences.edit()
                        .putString(AgentConfig.DEVICE_TOKEN, result.token)
                        .putString(AgentConfig.DEVICE_ID, result.deviceId)
                        .putString(AgentConfig.DEVICE_NAME, result.name)
                        .apply();
                runOnUiThread(() -> {
                    Toast.makeText(this, "配对成功", Toast.LENGTH_SHORT).show();
                    startAgentService();
                    refreshStatus();
                });
            } catch (Exception exc) {
                String message = exc.getMessage() == null ? exc.toString() : exc.getMessage();
                runOnUiThread(() -> {
                    detailView.setText("配对失败：" + message);
                    Toast.makeText(this, "配对失败", Toast.LENGTH_SHORT).show();
                });
            }
        }, "phone-agent-pair").start();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
