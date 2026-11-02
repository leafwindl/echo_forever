# Echo Desktop

独立的 Windows 电脑节点和桌面客户端。它不放进 Flutter App，也不复用后端 feature 的进程；通过出站 WebSocket 连接 Echo，执行本机操作，并在客户端里显示状态、动作和日志。

当前 MVP：

- 配对：一次性配对码，节点 token 保存在 `%APPDATA%\EchoDesktop\config.json`
- 打开：网易云音乐、记事本、计算器
- 媒体：播放/暂停、下一首、上一首
- 看屏幕：截图后由服务端视觉模型描述
- 看摄像头：单次抓拍后由服务端视觉模型描述，不持续录制

## 运行

在后端生成配对码：

```powershell
python scripts/create_desktop_pairing_code.py --phone +86137...
```

在电脑上：

```powershell
cd desktop_node
python -m echo_desktop pair --code 123456 --server https://api.echoaiforever.cn
```

之后双击 `desktop_node/start.cmd` 打开客户端，或：

```powershell
python -m echo_desktop client
```

也可以只用无界面模式：

```powershell
python -m echo_desktop run
```

本地开发时把 `--server` 换成 `http://127.0.0.1:8000`。

## 批准与日志

客户端默认开启 **“总是允许”**：Echo 打开应用、截图或看摄像头时不再弹本地批准窗口。这个开关可以随时在客户端里关闭；关闭后恢复每次询问。

客户端显示：

- 连接状态、服务器、节点名和节点 ID
- 最近一次电脑操作
- 每次连接、操作、失败和拒绝的日志
- 视觉/摄像头操作也会记录，但不保存图片

日志同时写到 `%APPDATA%\EchoDesktop\echo-desktop.log`，超过 1 MB 自动轮转一份旧日志。

## 扩展点

- `echo_desktop/actions/`：新增本机动作。
- `executor.py`：动作审批和调度。
- `client.py`：WebSocket 运行时。
- `gui.py`：客户端状态和日志界面。

新增动作仍应走后端白名单和工具合同，不在客户端里做任意命令执行。

## 当前边界

- 只支持 Windows。
- 只允许固定应用白名单，不接受任意命令行或任意路径。
- 视觉描述不写入记忆；图片不落盘。
- token 目前保存在本机配置文件中，尚未接入 Windows Credential Manager。
- 客户端是窗口程序，还没有系统托盘和开机自启。
- 总是允许会降低本机确认强度；摄像头和屏幕操作仍应只在用户明确要求时由 Echo 触发。
