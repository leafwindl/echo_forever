package cn.echoaiforever.phone_agent;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;

import org.json.JSONObject;

final class AgentCommandHandler {
    private AgentCommandHandler() {
    }

    static JSONObject handle(Context context, String action, JSONObject arguments) {
        try {
            if ("observe".equals(action)) {
                return observe();
            }
            if ("screenshot".equals(action)) {
                return screenshot();
            }
            if ("notifications".equals(action)) {
                return notifications();
            }
            if ("stop".equals(action)) {
                JSONObject data = new JSONObject();
                data.put("stopped", true);
                JSONObject result = new JSONObject();
                result.put("ok", true);
                result.put("data", data);
                return result;
            }
            if ("launch_app".equals(action)) {
                return launchApp(context, arguments.optString("package", ""));
            }
            if ("open_uri".equals(action)) {
                return openUri(context, arguments.optString("uri", ""));
            }
            if ("action".equals(action)) {
                return performAction(arguments);
            }
            return error("unsupported_action", "不支持的手机命令：" + action);
        } catch (Exception exc) {
            return error("command_failed", exc.getMessage() == null ? exc.toString() : exc.getMessage());
        }
    }

    private static JSONObject observe() throws Exception {
        AgentAccessibilityService service = AgentAccessibilityService.instance();
        if (service == null) {
            return error("accessibility_unavailable", "无障碍服务未连接");
        }
        JSONObject data = new JSONObject();
        data.put("text", service.dumpTree());
        data.put("package", service.currentPackage());
        data.put("class", service.currentWindow());
        JSONObject result = new JSONObject();
        result.put("ok", true);
        result.put("data", data);
        return result;
    }

    private static JSONObject screenshot() throws Exception {
        String image = AgentForegroundService.captureScreenshot();
        if (image.isEmpty()) {
            return error(
                    "screenshot_unavailable",
                    "ADB 截图桥不可用，请确认 PC 桥进程和 adb reverse 已启动"
            );
        }
        JSONObject data = new JSONObject();
        data.put("image_base64", image);
        data.put("mime", AgentForegroundService.captureScreenshotMime());
        data.put("source", "adb_bridge");
        JSONObject result = new JSONObject();
        result.put("ok", true);
        result.put("data", data);
        return result;
    }

    private static JSONObject notifications() throws Exception {
        JSONObject data = new JSONObject();
        data.put("notifications", AgentNotificationListener.snapshot());
        JSONObject result = new JSONObject();
        result.put("ok", true);
        result.put("data", data);
        return result;
    }

    private static JSONObject launchApp(Context context, String packageName) throws Exception {
        if (packageName == null || packageName.trim().isEmpty()) {
            return error("invalid_package", "缺少应用包名");
        }
        PackageManager manager = context.getPackageManager();
        Intent intent = manager.getLaunchIntentForPackage(packageName.trim());
        if (intent == null) {
            return error("app_not_found", "没有找到可启动的应用：" + packageName);
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
        JSONObject data = new JSONObject();
        data.put("package", packageName);
        JSONObject result = new JSONObject();
        result.put("ok", true);
        result.put("data", data);
        return result;
    }

    private static JSONObject openUri(Context context, String value) throws Exception {
        String uri = value == null ? "" : value.trim();
        if (!(uri.startsWith("http://")
                || uri.startsWith("https://")
                || uri.startsWith("orpheus://"))) {
            return error("invalid_uri", "只允许 http/https/orpheus URI");
        }
        if (!AgentInputBridge.openUri(uri)) {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(uri));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        }
        JSONObject data = new JSONObject();
        data.put("uri", uri);
        JSONObject result = new JSONObject();
        result.put("ok", true);
        result.put("data", data);
        return result;
    }

    private static JSONObject performAction(JSONObject arguments) throws Exception {
        String kind = arguments.optString("kind", "");
        if ("key".equals(kind)) {
            boolean success = AgentInputBridge.key(arguments.optInt("keycode", 0));
            return actionResult(kind, success);
        }
        AgentAccessibilityService service = AgentAccessibilityService.instance();
        if (service == null) {
            return error("accessibility_unavailable", "无障碍服务未连接");
        }
        boolean success;
        switch (kind) {
            case "tap":
                success = service.tap(
                        arguments.optInt("x", 0),
                        arguments.optInt("y", 0)
                );
                break;
            case "tap_text":
                success = service.clickByText(arguments.optString("text", ""));
                break;
            case "text":
                success = service.setFocusedText(arguments.optString("text", ""));
                if (!success) {
                    success = AgentInputBridge.typeText(arguments.optString("text", ""));
                }
                break;
            case "back":
            case "home":
            case "recents":
                success = service.performGlobal(kind);
                break;
            default:
                return error("unsupported_action_kind", "不支持的动作：" + kind);
        }
        return actionResult(kind, success);
    }

    private static JSONObject actionResult(String kind, boolean success) throws Exception {
        if (!success) {
            return error("action_failed", "手机动作没有成功执行：" + kind);
        }
        JSONObject data = new JSONObject();
        data.put("kind", kind);
        JSONObject result = new JSONObject();
        result.put("ok", true);
        result.put("data", data);
        return result;
    }

    private static JSONObject error(String code, String message) {
        try {
            JSONObject error = new JSONObject();
            error.put("code", code);
            error.put("message", message);
            JSONObject result = new JSONObject();
            result.put("ok", false);
            result.put("error", error);
            return result;
        } catch (Exception exc) {
            return new JSONObject();
        }
    }
}
