# Echo AI 伴侣微信小程序 Demo 技术迭代方案
> 版本：v0.2-Memory
> 目标：将 Echo 从“能记住最近几轮对话”的短期上下文，升级为“可控、可解释、可删除”的长期记忆系统
> 原则：先做稳定的记忆架构，再做复杂 RAG；先保证用户隔离和数据边界，再提高智能程度

***

## 1. v0.2 核心定位

v0.1 已完成 Echo 的基础对话能力，包括文本聊天、语音识别、语音回复、基础 SQLite 消息存储，以及最近 N 轮上下文拼接。

v0.2 的核心任务不是简单把所有聊天记录塞进向量库，而是建立一套真正适合 AI 伴侣产品的记忆系统：

- 短期记忆：当前会话最近几轮上下文
- 会话摘要：长对话压缩后的滚动摘要
- 长期记忆：从对话中抽取出的稳定事实、偏好、关系、目标
- 相关记忆检索：根据当前问题召回与本轮对话相关的长期记忆
- 用户可控：用户可以查看、删除、清空自己的记忆

工业上常见的 RAG 更适合“知识库问答”或“文档检索”。Echo 的长期记忆更接近 Memory-Augmented Chat，RAG/向量检索只是其中一部分。

***

## 2. 本期范围与边界

**本期包含**

- 修复用户身份体系，避免所有用户共享 `test_user_001`
- 抽出统一的对话上下文构建器，文本和语音共用同一套记忆逻辑
- 增加会话维度，支持当前会话、历史会话和会话摘要
- 增加结构化长期记忆表，用于保存用户偏好、事实、关系和目标
- 增加记忆抽取流程，从用户对话中提取“值得记住”的内容
- 增加记忆检索流程，把相关记忆注入 prompt
- 增加记忆管理接口，支持查看、删除、清空记忆
- 为向量库预留架构，并在 v0.2 后半段接入轻量向量检索

**本期不包含**

- 完整知识库 RAG 文件上传系统
- 多用户生产级权限体系
- 主动推送、日程提醒、外部工具调用
- 复杂情绪识别和心理健康诊断
- 大规模分布式向量数据库部署
- 端侧本地加密和端侧长期记忆

***

## 3. 当前问题梳理

### 3.1 用户身份问题

当前 `/login` 返回固定 `test_user_001`。这在记忆系统阶段是最高优先级问题。

如果多个真实用户共用同一个 `user_id`，长期记忆会发生串用户，导致：

- Echo 把 A 用户的信息说给 B 用户
- 用户画像污染
- 隐私风险
- 后续向量检索结果不可控

v0.2 必须先实现稳定用户标识，至少完成微信 `code2session` 换取 `openid`。

### 3.2 当前记忆只是短期上下文

当前 `services/memory.py` 保存所有聊天记录，但每次请求只加载最近 20 条消息。

这属于短期上下文窗口，不是真正的长期记忆。它的问题是：

- 聊天变长后早期信息会丢失
- 没有摘要，长对话成本越来越高
- 没有区分重要事实和普通闲聊
- 没有用户可控的删除能力
- 没有按当前语义检索相关记忆

### 3.3 文本和语音链路重复

当前 `/chat/send` 和 `/voice/reply` 都在各自函数里拼接 `messages`，逻辑重复。

v0.2 应统一为：

```text
用户输入文本
  -> build_chat_context(user_id, message)
  -> request_llm(messages)
  -> save chat messages
  -> memory post-processing
```

语音链路只负责 ASR 和 TTS，中间的对话与记忆逻辑应和文本完全复用。

***

## 4. v0.2 目标架构

```text
微信小程序
  |
  | 文本消息 / 语音消息
  v
FastAPI Backend
  |
  |-- Auth Service
  |     - 微信 code2session
  |     - user_id / openid 管理
  |
  |-- Chat Service
  |     - 统一处理文本和语音对话
  |     - 写入原始消息
  |
  |-- Context Builder
  |     - 系统人设
  |     - 用户画像
  |     - 长期记忆
  |     - 会话摘要
  |     - 最近上下文
  |
  |-- Memory Service
  |     - 原始消息存储
  |     - 会话摘要
  |     - 结构化记忆抽取
  |     - 相关记忆检索
  |     - 记忆删除和清空
  |
  |-- LLM Client
  |     - 对话生成
  |     - 记忆抽取
  |     - 摘要生成
  |
  |-- Vector Store Adapter
        - v0.2 MVP: 本地轻量向量库
        - 后续生产: PostgreSQL + pgvector
```

***

## 5. 数据模型设计

### 5.1 users

用于保存真实用户身份。

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    openid TEXT UNIQUE,
    nickname TEXT,
    avatar_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

说明：

- `user_id` 是后端内部稳定 ID
- `openid` 来自微信登录
- 开发阶段可以允许 `guest_xxx`，但不能所有用户共用同一个固定 ID

### 5.2 conversations

用于区分不同会话，并保存滚动摘要。

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    title TEXT,
    summary TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.3 chat_messages

当前已有表需要扩展。

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

新增字段：

- `conversation_id`：归属会话
- `message_type`：区分文本、语音 ASR 文本、系统消息等

### 5.4 user_memories

长期记忆表。

```sql
CREATE TABLE IF NOT EXISTS user_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_message_id INTEGER,
    confidence REAL DEFAULT 0.8,
    importance INTEGER DEFAULT 3,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME
);
```

`memory_type` 建议先分为：

| 类型 | 示例 | 说明 |
| --- | --- | --- |
| `profile` | 用户叫小安 | 稳定身份信息 |
| `preference` | 用户喜欢简洁回答 | 偏好 |
| `relationship` | 用户提到姐姐在上海 | 人际关系 |
| `goal` | 用户最近在准备考研 | 阶段目标 |
| `event` | 用户上周开始实习 | 重要事件 |
| `boundary` | 用户不喜欢被追问隐私 | 交互边界 |

### 5.5 memory_embeddings

向量检索预留表。v0.2 前半段可以先不启用，后半段接入。

```sql
CREATE TABLE IF NOT EXISTS memory_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    vector_store_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

如果使用本地 Chroma，可以把 `vector_store_id` 映射到 Chroma collection 中的文档 ID。

如果后续迁移 PostgreSQL + pgvector，可以直接把 embedding 存在数据库中。

***

## 6. Prompt 组装策略

v0.2 不再直接把最近 20 条消息简单塞给模型，而是通过 `Context Builder` 统一生成上下文。

推荐顺序：

```text
1. 系统人设
2. 安全与行为边界
3. 用户基础画像
4. 本轮相关长期记忆
5. 当前会话摘要
6. 最近若干轮原始消息
7. 当前用户消息
```

示例：

```text
系统人设：
你叫 Echo，是一位温柔、细腻、自然的 AI 伴侣。

用户画像：
- 用户希望被称呼为“小安”
- 用户偏好简洁但有温度的回答

相关长期记忆：
- 用户最近在准备考研，容易因为复习进度焦虑
- 用户晚上容易胃不舒服，不喜欢太晚吃东西

当前会话摘要：
用户刚刚在聊今天复习效率低，有点自责。

最近对话：
user: 今天一整天都没怎么学进去
assistant: 听起来你有点累，也可能不是完全“不努力”...

当前消息：
user: 我是不是太废了
```

### Token 预算建议

| 模块 | 预算 |
| --- | --- |
| 系统人设 | 500 到 800 tokens |
| 用户画像和长期记忆 | 800 到 1200 tokens |
| 会话摘要 | 500 到 1000 tokens |
| 最近上下文 | 2000 到 4000 tokens |
| 模型回复 | 当前保持 500 tokens |

v0.2 可以先按字符数近似控制，后续再接 tokenizer。

***

## 7. 记忆抽取策略

### 7.1 什么时候抽取

每轮对话结束后，异步执行记忆抽取。

输入：

- 用户本轮消息
- AI 本轮回复
- 最近几轮上下文

输出：

- 是否需要新增记忆
- 是否需要更新已有记忆
- 是否需要忽略

### 7.2 哪些内容值得记住

应该记住：

- 用户明确表达的长期偏好
- 用户主动告知的身份信息
- 用户反复出现的目标或压力源
- 用户重要关系和称呼
- 用户对 Echo 交互方式的要求
- 用户明确说“你要记住”的内容

不应该记住：

- 一次性的普通情绪
- 明显玩笑或反讽
- AI 自己推测出来但用户没有确认的信息
- 敏感信息，除非用户明确要求记住
- 用户明确说“不用记”“忘掉这个”的内容

### 7.3 抽取 Prompt 输出格式

要求 LLM 输出 JSON，便于后端解析。

```json
{
  "memories": [
    {
      "action": "create",
      "memory_type": "preference",
      "content": "用户喜欢 Echo 用简洁但有温度的方式回复。",
      "confidence": 0.9,
      "importance": 4
    }
  ]
}
```

### 7.4 去重与更新

新增记忆前需要先查同类型已有记忆。

规则：

- 内容相同：不重复写入，只更新 `updated_at`
- 内容冲突：旧记忆标记为 `inactive`，新记忆写入
- 内容更具体：合并为更完整版本
- 用户明确纠正：优先相信用户最新表达

***

## 8. 向量库方案

### 8.1 v0.2 推荐路线

v0.2 不建议一开始就搭完整知识库 RAG。推荐分两步：

第一步：结构化长期记忆，不使用向量库也能工作。

第二步：只对 `user_memories.content` 做 embedding 和向量检索，而不是对所有原始聊天记录做向量化。

### 8.2 本地 Demo 方案

本地开发优先使用：

- SQLite：保存用户、会话、消息、结构化记忆
- Chroma：保存长期记忆 embedding
- 后端封装 `VectorStoreAdapter`，避免以后迁移时大改业务代码

### 8.3 生产迁移方案

生产环境建议：

- PostgreSQL：主业务数据
- pgvector：长期记忆向量
- Redis：短期缓存和任务队列

原因：

- 用户隔离、权限、事务更容易做
- 向量和关系数据可以放在一个数据库里管理
- 后续部署和备份更稳定

***

## 9. 后端模块拆分

建议新增或重构如下模块。

```text
Echo-backend/
  services/
    auth.py
    memory.py
    conversation.py
    context_builder.py
    memory_extractor.py
    vector_store.py
    embedding_client.py
```

### 9.1 auth.py

负责：

- 微信 `code2session`
- 创建或读取用户
- 返回稳定 `user_id`

### 9.2 conversation.py

负责：

- 创建会话
- 查询会话
- 更新会话摘要
- 清空当前会话上下文

### 9.3 context_builder.py

负责：

- 查询最近消息
- 查询会话摘要
- 查询相关长期记忆
- 拼装最终 messages

### 9.4 memory_extractor.py

负责：

- 调用 LLM 抽取记忆
- 解析 JSON
- 去重、合并、更新记忆

### 9.5 vector_store.py

负责：

- 写入 memory embedding
- 按 `user_id` 和 query 检索相关记忆
- 隐藏 Chroma 或 pgvector 的实现差异

***

## 10. API 设计

### 10.1 保留接口

- `POST /login`
- `POST /chat/send`
- `POST /voice/asr`
- `POST /voice/reply`

### 10.2 新增接口

#### 获取聊天历史

```http
GET /chat/history?conversation_id=xxx
```

返回当前会话消息。

#### 清空当前会话上下文

```http
POST /chat/clear-context
```

只清空当前会话或新建一个会话，不删除长期记忆。

#### 获取长期记忆

```http
GET /memory/list
```

返回用户当前 active 的长期记忆。

#### 删除单条长期记忆

```http
DELETE /memory/{memory_id}
```

将记忆标记为 `deleted` 或 `inactive`。

#### 清空长期记忆

```http
POST /memory/clear
```

清空当前用户长期记忆，不删除聊天原始记录。

#### 清空全部用户数据

```http
POST /user/delete-data
```

删除或软删除该用户的消息、会话、长期记忆和向量数据。

***

## 11. 前端改造任务

### 11.1 聊天页

- 文本聊天继续走 `/chat/send`
- 语音链路继续走 `/voice/asr` + `/voice/reply`
- 新增 `conversation_id` 存储
- `清除上下文` 按钮改为调用后端 `/chat/clear-context`
- 当 Echo 使用记忆时，可以暂时不在 UI 显示，避免打扰体验

### 11.2 记忆管理页

新增一个轻量设置入口：

- 查看 Echo 记住了什么
- 删除单条记忆
- 清空全部长期记忆
- 清空聊天记录

### 11.3 首次引导

首次登录后，Echo 引导用户告诉它：

- 希望被怎么称呼
- 喜欢什么样的回复方式
- 是否允许 Echo 记住长期偏好

这部分可以作为第一批结构化记忆写入 `user_memories`。

***

## 12. 实施路线图

### 阶段 1：用户隔离与数据模型

目标：记忆系统不会串用户。

任务：

- 实现微信 `code2session`
- 创建 `users` 表
- 生成稳定 `user_id`
- 扩展 `chat_messages`
- 新增 `conversations`
- 新增 `user_memories`

交付标准：

- 不同微信用户拥有不同 `user_id`
- 聊天记录按用户隔离
- 文本和语音消息都能正确写入同一套消息表

### 阶段 2：统一上下文构建

目标：文本和语音共享同一套对话逻辑。

任务：

- 新增 `context_builder.py`
- 重构 `/chat/send`
- 重构 `/voice/reply`
- 把最近消息、会话摘要、长期记忆统一拼装

交付标准：

- `/chat/send` 和 `/voice/reply` 不再重复拼接 prompt
- 后续记忆能力只需要接入 `Context Builder`

### 阶段 3：会话摘要

目标：长文本对话不会无限增长上下文。

任务：

- 为每个会话维护 `summary`
- 当会话超过指定轮数时自动摘要旧消息
- 最近消息只保留最后 N 轮进入 prompt

交付标准：

- 连续 30 轮以上对话后，Echo 仍能理解早期话题
- prompt 不会随着聊天轮数无限增长

### 阶段 4：结构化长期记忆

目标：Echo 能记住跨会话稳定信息。

任务：

- 新增 `memory_extractor.py`
- 每轮对话后异步抽取记忆
- 支持新增、更新、去重、冲突处理
- 支持手动写入首次引导信息

交付标准：

- 用户说“以后叫我小安”，下次新会话 Echo 仍能使用该称呼
- 用户说“我喜欢你回答简洁一点”，后续回复风格能明显变化
- 用户纠正信息时，旧记忆不会继续生效

### 阶段 5：向量检索

目标：当前问题能召回相关长期记忆。

任务：

- 新增 `embedding_client.py`
- 新增 `vector_store.py`
- 对 `user_memories.content` 生成 embedding
- 每轮对话按当前消息召回 top-k 相关记忆
- 只允许召回当前 `user_id` 的记忆

交付标准：

- 不把无关记忆塞进 prompt
- 检索结果可记录、可调试
- 用户删除记忆后，向量库中对应记录也失效

### 阶段 6：记忆管理和隐私控制

目标：用户可以控制 Echo 记住什么。

任务：

- 新增 `/memory/list`
- 新增 `/memory/{memory_id}` 删除
- 新增 `/memory/clear`
- 新增 `/chat/clear-context`
- 前端增加记忆管理入口

交付标准：

- 用户能看到长期记忆列表
- 用户删除某条记忆后，Echo 不再使用
- 清空上下文和清空长期记忆语义明确区分

***

## 13. 验收用例

### 用例 1：用户隔离

步骤：

1. 用户 A 登录并告诉 Echo：“我叫小安”
2. 用户 B 登录并开始聊天
3. 用户 B 问：“你记得我叫什么吗？”

预期：

- Echo 不应回答“小安”
- 两个用户聊天记录和长期记忆完全隔离

### 用例 2：跨会话称呼记忆

步骤：

1. 用户告诉 Echo：“以后叫我小安吧”
2. 开启新会话
3. 用户问：“你还记得怎么叫我吗？”

预期：

- Echo 能自然称呼用户为“小安”

### 用例 3：记忆删除

步骤：

1. 用户删除“叫我小安”的记忆
2. 开启新会话
3. 用户问：“你还记得我的称呼吗？”

预期：

- Echo 不再使用已删除称呼

### 用例 4：长对话摘要

步骤：

1. 连续聊天超过 30 轮
2. 用户回到最开始的话题

预期：

- Echo 可以通过会话摘要理解早期内容
- prompt 长度稳定，不无限增长

### 用例 5：语音与文本共享记忆

步骤：

1. 用户通过语音说：“我最近在准备考研”
2. 用户通过文字问：“我现在为什么这么焦虑？”

预期：

- Echo 能结合“准备考研”的长期记忆回答

***

## 14. 风险与控制

| 风险 | 表现 | 控制方式 |
| --- | --- | --- |
| 串用户 | A 用户记忆出现在 B 用户对话中 | v0.2 第一阶段先做用户身份隔离 |
| 误记忆 | Echo 把玩笑、临时情绪当作长期事实 | 记忆抽取设置严格规则和 confidence |
| 记忆污染 | 旧信息和新信息冲突 | 使用 status、updated_at 和冲突更新规则 |
| 隐私风险 | 用户无法删除被记住的信息 | 提供记忆列表、删除、清空接口 |
| 成本上升 | 每轮都做抽取和 embedding | 抽取异步化，必要时每几轮批处理 |
| 延迟上升 | 检索和抽取影响回复速度 | 回复先返回，记忆处理后台执行 |
| 检索误召回 | 不相关记忆进入 prompt | 设置 top-k、分数阈值、类型过滤 |

***

## 15. v0.2 交付物

### 后端交付

- 用户身份隔离
- 会话数据模型
- 统一上下文构建器
- 会话摘要能力
- 结构化长期记忆能力
- 记忆抽取与更新能力
- 记忆管理 API
- 向量检索适配器 MVP

### 前端交付

- 正确传递稳定 `user_id`
- 正确维护 `conversation_id`
- 清空上下文按钮接入后端
- 记忆管理页 MVP
- 首次引导收集称呼和偏好

### 文档交付

- 数据库表结构说明
- API 文档
- 记忆抽取 Prompt
- Prompt 组装规则
- 隐私和删除策略说明

***

## 16. 推荐开发顺序

1. 用户身份真实化
2. 数据库表结构迁移
3. 文本和语音链路统一到 Chat Service
4. Context Builder
5. 会话摘要
6. 结构化长期记忆
7. 记忆管理接口
8. 记忆管理前端
9. embedding 和向量检索
10. 验收测试和日志观测

这个顺序的核心原因是：长期记忆越强，越需要先保证用户隔离、数据边界和可删除能力。否则能力越强，风险越大。

***

## 17. v0.2 完成后的状态

完成 v0.2 后，Echo 应具备以下能力：

- 能区分不同用户，不串记忆
- 能记住用户明确告诉它的重要信息
- 能在新会话中使用长期记忆
- 能处理较长对话，不依赖无限拼接原始历史
- 用户能查看和删除 Echo 记住的内容
- 文本和语音共享同一套记忆系统
- 后续可以自然扩展到知识库 RAG、App 端侧记忆、主动交互和更复杂的人格系统

v0.2 的目标不是让 Echo “记住一切”，而是让 Echo “记得该记的，并且用户知道它记住了什么”。
