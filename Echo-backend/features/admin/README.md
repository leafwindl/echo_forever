# Admin 模块

## 1. 业务目标

提供内部调试和管理能力。当前只用于调试系统提示词和清空聊天上下文，默认关闭，不面向普通用户。

## 2. 核心业务流程

1. 管理员请求调试接口，并携带 `X-Admin-Debug-Token`。
2. Interface 校验 `ENABLE_ADMIN_DEBUG_API` 和 token。
3. Application 校验输入并执行管理用例。
4. Infrastructure 读写运行时配置或清理聊天上下文。
5. Chat 构建上下文时优先读取运行时系统提示词，没有配置时回退到 `.env` 默认值。

## 3. 对外契约

### HTTP API

- `GET /admin/debug/prompt`
  - 查看当前生效系统提示词和来源。
- `PUT /admin/debug/prompt`
  - 更新运行时系统提示词。
- `POST /admin/debug/chat/clear`
  - 清空指定用户聊天消息并重置会话摘要，不清长期记忆。

### 依赖的其它模块接口

- Chat 模块：读取当前生效系统提示词。
- SQLite：保存运行时配置并清理聊天上下文。

## 4. 数据库表

- `runtime_settings`
- `chat_messages`
- `conversations`

## 5. 关键配置项

- `ENABLE_ADMIN_DEBUG_API`
- `ADMIN_DEBUG_TOKEN`

## 6. 注意事项

- 外测和生产环境必须关闭 `ENABLE_ADMIN_DEBUG_API`。
- `ADMIN_DEBUG_TOKEN` 不要提交真实值。
- 清空聊天上下文不会删除长期记忆。
