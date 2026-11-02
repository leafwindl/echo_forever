# desktop

Windows 电脑节点能力。它与 `devices`（Echo 音箱/语音设备）分开：这里管理的是用户 PC 上的 Echo Desktop 进程。

## 边界

- `POST /desktop/nodes/pair`：一次性配对码换取节点 token；不依赖用户登录，配对码本身是短期凭证。
- `GET /desktop/nodes`：当前用户已配对节点和在线状态。
- `DELETE /desktop/nodes/{node_id}`：撤销节点并关闭在线连接。
- `WS /desktop/nodes/ws`：节点出站连接，`Authorization: Bearer <node_token>`；服务端下发命令，节点在本地弹窗批准后执行。
- Agent 工具：`desktop_open_app`、`desktop_media_control`、`desktop_look`、`desktop_screenshot`、`desktop_status`。

## 安全

- 节点 token 只保存哈希，原始 token 只在配对响应返回一次。
- 所有动作都有 `desktop_actions` 审计记录；不保存截图、摄像头图片或原始 token。
- 电脑端每次动作都要本地批准；摄像头/屏幕没有后台持续采集路径。
- 应用白名单固定，当前不接受任意命令行或任意路径。
- 视觉结果只把文字描述交给对话模型；原始图片在工具返回前丢弃。

## 配对码

```powershell
python scripts/create_desktop_pairing_code.py --phone +86137...
```

配对码默认 10 分钟有效、一次性使用；脚本是当前运维入口，后续再接入 App 设置页。
