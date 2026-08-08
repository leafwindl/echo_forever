# Getui / 国内 Android 推送配置

Echo 使用个推作为国内 Android 主推送通道，Firebase 不再参与 Android 构建。

## 本地凭证

后端 `Echo-backend/.env` 只保存服务端凭证：

```env
PUSH_ENABLED=true
GETUI_APP_ID=
GETUI_APP_KEY=
GETUI_MASTER_SECRET=
GETUI_API_BASE_URL=https://restapi.getui.com/v2
```

Android 只需要 AppID。将它写入未纳入 Git 的 `app/android/local.properties`：

```properties
echo.getuiAppId=
```

`AppKey` 和 `MasterSecret` 不得放进 APK、Dart 源码或日志。

## Android 应用信息

个推控制台中的 Android 包名必须是：

```text
cn.echoaiforever.echo_app
```

应用首次获得通知授权后，APP 获取 CID 并调用 `PUT /push/tokens/me`。后端只向当前账号的 active Getui CID 发送 Outbox 通知。

## 构建

```powershell
flutter pub get
flutter build apk --debug
```

个推 Flutter 插件源码固定在 `third_party/getuiflut`，避免依赖 Pub 缓存中的旧 Gradle 配置。厂商离线通道需要后续分别配置华为、荣耀、小米、OPPO、vivo 等平台凭证；没有厂商凭证时仍可先验证个推主通道。
