# User Preferences Feature

保存用户主动填写的称呼和回复偏好，并向 Chat 提供结构化、低权限的个性化数据。

HTTP 路径沿用产品术语 `persona`，领域模型统一命名为 `UserPreferences`；它表示用户偏好，不是 Echo 的助手人格。

边界：

- Persona 是显式设置，不等同于模型从聊天中抽取的长期记忆。
- `relationship_pace` 和 `affection_style` 只限定关系表达节奏和上限，不能直接提升关系阶段。
- Echo 固定人格由 `features.assistant_persona` 维护，动态关系由 `features.relationship` 维护。
- 重置 Persona 不会清理记忆、聊天记录或会话摘要。
- 没有偏好记录时 `onboarding_completed=false`；首次保存后变为 `true`。恢复默认偏好不会再次触发首次引导。
- 外部模块只能经 `features.persona.public` 访问本模块。
- 自由文本在 Prompt Renderer 中经过边界转义，只能作为背景数据，不能覆盖安全规则。
- HTTP API 仅使用 Bearer Token 解析出的当前用户，不接受客户端指定 `user_id`。

接口：

- `GET /persona/me`
- `PUT /persona/me`
- `POST /persona/me/reset`
