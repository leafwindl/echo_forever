package cn.echoaiforever.phone_agent;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Rect;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

public class AgentAccessibilityService extends AccessibilityService {
    private static volatile AgentAccessibilityService instance;
    private String lastPackage = "";
    private String lastWindow = "";

    public static AgentAccessibilityService instance() {
        return instance;
    }

    @Override
    public void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) {
            return;
        }
        if (event.getPackageName() != null) {
            lastPackage = event.getPackageName().toString();
        }
        if (event.getClassName() != null) {
            lastWindow = event.getClassName().toString();
        }
    }

    @Override
    public void onInterrupt() {
        // No long-running gesture is active in this skeleton.
    }

    @Override
    public void onDestroy() {
        instance = null;
        super.onDestroy();
    }

    public String describeState() {
        return "package=" + lastPackage + "\nclass=" + lastWindow;
    }

    public String dumpTree() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) {
            return "当前没有可读窗口（可能已锁屏，或当前应用禁止无障碍读取）。";
        }
        StringBuilder builder = new StringBuilder();
        builder.append("package=").append(lastPackage)
                .append("  class=").append(lastWindow).append("\n\n");
        Deque<NodeDepth> stack = new ArrayDeque<>();
        stack.push(new NodeDepth(root, 0));
        int count = 0;
        while (!stack.isEmpty() && count < 300) {
            NodeDepth current = stack.pop();
            AccessibilityNodeInfo node = current.node;
            String label = labelOf(node);
            Rect bounds = new Rect();
            node.getBoundsInScreen(bounds);
            if (!label.isEmpty()) {
                builder.append(indent(Math.min(current.depth, 8)))
                        .append(label)
                        .append("  [").append(bounds.left).append(',').append(bounds.top)
                        .append("][").append(bounds.right).append(',').append(bounds.bottom)
                        .append(']')
                        .append(node.isClickable() ? "  CLICK" : "")
                        .append('\n');
                count++;
            }
            for (int index = node.getChildCount() - 1; index >= 0; index--) {
                AccessibilityNodeInfo child = node.getChild(index);
                if (child != null) {
                    stack.push(new NodeDepth(child, current.depth + 1));
                }
            }
        }
        return builder.toString();
    }

    public boolean clickByText(String query) {
        if (query == null || query.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) {
            return false;
        }
        AccessibilityNodeInfo found = find(
                root,
                query.toLowerCase(Locale.ROOT),
                0
        );
        if (found == null) {
            return false;
        }
        AccessibilityNodeInfo clickable = found;
        while (clickable != null && !clickable.isClickable()) {
            clickable = clickable.getParent();
        }
        return (clickable != null ? clickable : found).performAction(
                AccessibilityNodeInfo.ACTION_CLICK
        );
    }

    private AccessibilityNodeInfo find(AccessibilityNodeInfo node, String query, int depth) {
        if (node == null || depth > 30) {
            return null;
        }
        String label = labelOf(node).toLowerCase(Locale.ROOT);
        if (label.contains(query)) {
            return node;
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            AccessibilityNodeInfo match = find(child, query, depth + 1);
            if (match != null) {
                return match;
            }
        }
        return null;
    }

    private String indent(int depth) {
        StringBuilder builder = new StringBuilder();
        for (int index = 0; index < depth; index++) {
            builder.append("  ");
        }
        return builder.toString();
    }

    private String labelOf(AccessibilityNodeInfo node) {
        CharSequence text = node.getText();
        if (text != null && !text.toString().isEmpty()) {
            return text.toString();
        }
        CharSequence description = node.getContentDescription();
        if (description != null && !description.toString().isEmpty()) {
            return description.toString();
        }
        String viewId = node.getViewIdResourceName();
        return viewId != null ? viewId : "";
    }

    private static final class NodeDepth {
        final AccessibilityNodeInfo node;
        final int depth;

        NodeDepth(AccessibilityNodeInfo node, int depth) {
            this.node = node;
            this.depth = depth;
        }
    }
}
