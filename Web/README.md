# Echo Mini Program 1.0

原生微信小程序，TypeScript + Sass。

## 页面

- `onboarding`：建立会话并强制新用户完成首次个性化。
- `chat`：人物展示和纯文字聊天。
- `call`：独立电话界面、录音、ASR、口语对话和 TTS 播放。
- `persona`：编辑完整用户偏好和重置关系。
- `memory`：查看、删除和清空长期记忆。

## 依赖规则

```text
pages -> services / utils
services -> utils
utils 不依赖页面
```

- `utils/session.ts` 唯一负责微信登录和本地 Token 生命周期。
- `utils/api.ts` 唯一负责 HTTP 数据契约和 Bearer Header。
- `services/voice-*` 负责录音识别链路，`services/audio-player.ts` 负责顺序播放和停止。
- Chat 不导入语音服务；Call 不维护文字消息列表。

## 环境

API 域名在 `miniprogram/utils/env.ts` 按 `develop`、`trial`、`release` 选择。开发者工具打开本目录，项目根为 `miniprogram/`。

严格类型检查：

```bash
npm install
npx tsc --noEmit
```
