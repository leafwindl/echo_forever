# Echo App 1.0

Echo 的 Flutter 客户端，当前发布目标为 Android APK `1.0.0+1`。客户端按 `core / features / shared` 分层，网络请求和会话由 core 统一管理，各业务模块在自己的 data/domain/presentation 目录内闭合。

## 本地运行

```bash
flutter pub get
flutter run -d <device> --dart-define=ECHO_BASE_URL=http://localhost:8000
```

生产 APK：

```bash
flutter build apk --release \
  --dart-define=ECHO_ENV=production \
  --dart-define=ECHO_BASE_URL=https://api.example.com \
  --dart-define=APP_VERSION=1.0.0
```

## 客户端约定

- 登录使用手机号验证码，token 保存于 secure storage。
- 聊天支持文字和独立表情包消息；回复中的文字和图片分开渲染。
- 通话采集 16 kHz、单声道 PCM16LE，优先 WebSocket 流式 ASR，失败时上传整段 PCM。
- 通话使用 `mode=call` 获取 CosyVoice 音频，不发送表情包。
- 角色显示资源位于 `assets/character/`。

## 检查

```bash
flutter analyze
flutter test
```
