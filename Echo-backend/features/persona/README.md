# Persona Feature

保存用户主动填写的称呼和回复偏好，并向 Chat 提供结构化、低权限的个性化数据。

边界：

- Persona 是显式设置，不等同于模型从聊天中抽取的长期记忆。
- 重置 Persona 不会清理记忆、聊天记录或会话摘要。
- 外部模块只能经 `features.persona.public` 访问本模块。
- 自由文本在 Prompt Renderer 中经过边界转义，只能作为背景数据，不能覆盖安全规则。
- HTTP API 仅使用 Bearer Token 解析出的当前用户，不接受客户端指定 `user_id`。

接口：

- `GET /persona/me`
- `PUT /persona/me`
- `POST /persona/me/reset`
