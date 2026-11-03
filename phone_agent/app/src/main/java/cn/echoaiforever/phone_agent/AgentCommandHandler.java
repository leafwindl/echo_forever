package cn.echoaiforever.phone_agent;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;

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
            return error("screenshot_unavailable", "尚未授权截图，或当前屏幕不可截取");
        }
        JSONObject data = new JSONObject();
        data.put("image_base64", image);
        data.put("mime", "image/jpeg");
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

    private static JSONObject performAction(JSONObject arguments) throws Exception {
        AgentAccessibilityService service = AgentAccessibilityService.instance();
        if (service == null) {
            return error("accessibility_unavailable", "无障碍服务未连接");
        }
        String kind = arguments.optString("kind", "");
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
                break;
            case "back":
            case "home":
            case "recents":
                success = service.performGlobal(kind);
                break;
            default:
                return error("unsupported_action_kind", "不支持的动作：" + kind);
        }
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
