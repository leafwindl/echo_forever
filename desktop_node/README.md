# Echo Desktop

独立的 Windows 电脑节点。它不放进 Flutter App，也不复用后端 feature 的进程；通过出站 WebSocket 连接 Echo，执行经过本机弹窗批准的操作。

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
python -m echo_desktop run
```

本地开发时把 `--server` 换成 `http://127.0.0.1:8000`。

每次操作都会在 Windows 上弹出一个本地批准窗口；拒绝就不会执行。摄像头和截图默认每次询问，不会后台持续采集。

## 当前边界

- 只支持 Windows。
- 只允许固定应用白名单，不接受任意命令行或任意路径。
- 视觉描述不写入记忆；图片不落盘。
- token 目前保存在本机配置文件中，尚未接入 Windows Credential Manager。
