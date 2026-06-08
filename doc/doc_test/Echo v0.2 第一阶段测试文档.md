# Echo v0.2 第一阶段测试文档
> 阶段：1. 用户身份真实化 + 数据库表结构迁移
> 目标：验证不同用户不再共用 `test_user_001`，并确认后续记忆系统所需基础表已建立

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- `/login` 不再固定返回 `test_user_001`
- 微信配置完整时，后端通过 `code2session` 获取 `openid`
- 微信配置缺失时，后端使用前端传入的 `client_id` 生成稳定开发用户 ID
- 小程序端生成并缓存本地匿名 `client_id`
- 登录失败时，小程序不再使用固定 `guest`，而是使用本地稳定匿名 ID
- `chat_messages` 表增加 `conversation_id` 和 `message_type`
- 新增 `users`、`conversations`、`user_memories` 表

***

## 2. 测试前准备

### 2.1 后端环境

进入后端目录：

```bash
cd Echo-backend
```

启动服务：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2.2 数据库位置

当前 SQLite 数据库文件：

```text
Echo-backend/echo_memory.db
```

该文件已被 `.gitignore` 忽略，不应提交。

### 2.3 微信配置

真实微信登录需要 `.env` 中配置：

```dotenv
WECHAT_APPID=你的微信小程序 AppID
WECHAT_SECRET=你的微信小程序 Secret
```

如果这两个值为空，后端会进入开发兜底模式：使用小程序端传入的 `client_id` 生成 `dev_...` 用户 ID。

***

## 3. 测试用例

### 用例 1：本地开发兜底登录

**前提**

- `.env` 中 `WECHAT_APPID` 或 `WECHAT_SECRET` 为空

**请求**

```http
POST /login
Content-Type: application/json
```

```json
{
  "code": "mock_code_001",
  "client_id": "anon_device_a"
}
```

**预期**

- 返回 200
- 返回体包含 `user_id`
- `user_id` 以 `dev_` 开头
- 同一个 `client_id` 多次请求返回同一个 `user_id`
- 不同 `client_id` 返回不同 `user_id`

### 用例 2：真实微信登录

**前提**

- `.env` 中配置真实 `WECHAT_APPID`
- `.env` 中配置真实 `WECHAT_SECRET`
- 小程序端通过 `wx.login()` 获取真实 code

**操作**

1. 打开小程序
2. 触发 `wx.login()`
3. 小程序调用 `/login`

**预期**

- 返回 200
- 返回体包含 `user_id`
- `user_id` 以 `wx_` 开头
- 同一个微信用户每次登录返回同一个 `user_id`
- 不同微信用户返回不同 `user_id`

### 用例 3：前端本地匿名 ID

**操作**

1. 打开小程序聊天页
2. 查看本地存储 `echo_client_id`
3. 关闭并重新打开小程序
4. 再次查看 `echo_client_id`

**预期**

- 首次打开时生成 `anon_...` 格式的 `client_id`
- 重新打开后 `client_id` 不变
- 登录失败时页面 `userId` 使用该 `client_id`
- 代码中不再出现固定 `guest` 或 `test_user_001` 兜底

### 用例 4：数据库表结构迁移

**操作**

启动后端后检查 SQLite 表。

可用 SQLite 客户端执行：

```sql
.tables
```

**预期至少包含**

```text
users
conversations
chat_messages
user_memories
```

检查 `chat_messages` 字段：

```sql
PRAGMA table_info(chat_messages);
```

**预期包含**

- `id`
- `user_id`
- `conversation_id`
- `role`
- `content`
- `message_type`
- `timestamp`

### 用例 5：聊天消息自动补用户记录

**操作**

1. 使用任意 `user_id` 调用 `/chat/send`
2. 查询 `users` 表

```sql
SELECT user_id FROM users WHERE user_id = '你的 user_id';
```

**预期**

- 即使该用户不是通过 `/login` 创建，只要发生聊天写入，也会自动补齐 `users` 表记录

### 用例 6：用户隔离基础验证

**操作**

1. 用户 A 登录，得到 `user_id = A`
2. 用户 A 发送消息：“我叫小安”
3. 用户 B 登录，得到 `user_id = B`
4. 用户 B 发送消息：“你知道我叫什么吗？”

**预期**

- A 和 B 的 `user_id` 不相同
- `chat_messages` 中 A 和 B 的消息按不同 `user_id` 存储
- B 的历史上下文不会加载 A 的消息

***

## 4. 回归检查

### 4.1 文本聊天

**操作**

发送一条文本消息。

**预期**

- `/chat/send` 正常返回 AI 回复
- 用户消息和 AI 回复都写入 `chat_messages`

### 4.2 语音聊天

**操作**

录音并发送语音消息。

**预期**

- `/voice/asr` 正常返回 `user_text`
- `/voice/reply` 正常返回 `reply` 和 `audio_url`
- `/voice/reply` 使用当前页面 `userId`，不再回退到 `test_user_001`

***

## 5. 本阶段通过标准

第一阶段验收通过需要同时满足：

- 后端 `/login` 不再返回固定 `test_user_001`
- 小程序端不再使用固定 `guest` 或 `test_user_001`
- 不同微信用户或不同本地 `client_id` 会得到不同 `user_id`
- `users`、`conversations`、`chat_messages`、`user_memories` 表存在
- 旧 `chat_messages` 数据不会因为迁移被删除
- 文本和语音聊天仍能按原流程工作

***

## 6. 后续阶段入口

第一阶段完成后，可以进入第二阶段：

```text
文本和语音链路统一到 Chat Service
```

第二阶段重点不是新增记忆能力，而是先把 `/chat/send` 和 `/voice/reply` 的重复对话逻辑抽到统一服务中，为 `Context Builder` 和长期记忆注入做准备。
