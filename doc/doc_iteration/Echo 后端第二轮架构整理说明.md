# Echo 后端第二轮架构整理说明

## 目标

第二轮整理聚焦数据层边界和事务边界。第一轮已经把 HTTP 入口拆成 router/schema；这一轮继续把 SQL、连接管理和业务服务拆开，让后续迁移 PostgreSQL、引入任务队列或扩展数据模型时，不必在业务服务里到处改 SQL。

## 改了什么

### 1. 新增 `db` 模块

新增：

- `Echo-backend/db/connection.py`
- `Echo-backend/db/schema.py`

`connection.py` 负责：

- 统一计算数据库路径
- 创建 SQLite 连接
- 配置 `foreign_keys` 和 `busy_timeout`
- 提供 `transaction()` 事务上下文

`schema.py` 负责：

- 初始化表结构
- 执行兼容旧库的非破坏性字段补齐
- 创建索引
- 启用 SQLite WAL 模式

数据库默认路径现在固定为 `Echo-backend/echo_memory.db`，不再受进程启动目录影响。测试可通过 `ECHO_DB_PATH` 指向临时数据库。

### 2. 新增 repository 层

新增：

- `Echo-backend/repositories/user_repository.py`
- `Echo-backend/repositories/conversation_repository.py`
- `Echo-backend/repositories/message_repository.py`
- `Echo-backend/repositories/memory_repository.py`
- `Echo-backend/repositories/vector_repository.py`

拆分后，各 repository 的职责如下：

- `user_repository`：用户 upsert
- `conversation_repository`：会话创建、active 会话获取、摘要读写
- `message_repository`：聊天消息读写、短期历史读取
- `memory_repository`：长期记忆增删改查
- `vector_repository`：记忆 embedding 记录增删查

这样 SQL 不再集中堆在一个 `services/memory.py` 里，也不会让向量模块直接拿私有 `_connect` 操作数据库。

### 3. 保留 `services.memory` 兼容门面

`Echo-backend/services/memory.py` 已被压缩为兼容导出层。现有业务模块仍可以继续：

```python
from services.memory import list_user_memories
```

但真实实现已经下沉到 repository。这样可以分阶段迁移，不需要一次性修改所有业务代码。

### 4. 为一轮聊天建立原子写入

新增 `repositories.message_repository.add_chat_turn()`，并让 `services/chat.py` 使用它。

现在一次聊天中：

- user 消息写入
- assistant 消息写入
- conversation `updated_at` 更新

会在同一个事务上下文里完成。后续即使继续扩展 token usage、消息元数据、审计记录，也可以围绕这个事务边界扩展。

### 5. 向量存储 SQL 下沉

`services/vector_store.py` 不再直接 import `services.memory._connect`，而是通过 `repositories/vector_repository.py` 读写 `memory_embeddings` 表。

这让 `vector_store` 更像“向量召回算法和 embedding 编排层”，而不是数据库访问层。后续迁移 pgvector 或 Chroma 时，替换 repository/adapter 会更直接。

### 6. 补充 repository 测试

新增 `Echo-backend/tests/test_repositories.py`，使用临时 SQLite 文件验证：

- `init_db()` 能在临时库建表
- `add_chat_turn()` 能写入一轮 user/assistant 消息
- 长期记忆清空使用软删除
- embedding 记录可以写入和读取

这些测试不触碰真实 `echo_memory.db`。

## 怎么改的

### 数据连接

将原先 `services/memory.py` 中的 `_connect()` 迁移到：

```python
db.connection.get_connection()
```

并新增：

```python
db.connection.transaction()
```

repository 函数如果没有传入现有连接，就自己开启事务；如果传入连接，则参与外层事务。这样既保留简单调用方式，也允许服务层组合多个写操作。

### 建表迁移

将原先 `init_db()` 中的建表和索引逻辑迁移到：

```python
db.schema.init_db()
```

`main.py` 仍然通过 `services.memory.init_db` 调用，所以启动流程保持兼容。

### 业务调用

`services/chat.py` 从原来的两次 `add_message()`：

```python
user_message_id = add_message(...)
assistant_message_id = add_message(...)
```

改成：

```python
user_message_id, assistant_message_id = add_chat_turn(...)
```

这使一轮对话的核心写入拥有明确事务边界。

## 为什么这么改

### 降低 SQL 和业务编排耦合

业务服务应该描述“对话如何发生”“记忆什么时候抽取”，不应该同时维护建表、索引、SQL 查询细节。repository 层拆出后，业务服务更高内聚，数据访问更可替换。

### 给数据库迁移留空间

当前仍使用 SQLite，但连接、事务、schema、repository 已经有独立边界。后续迁移 PostgreSQL 时，可以优先替换 `db` 和 repository，而不用大面积改动 router 和 service。

### 明确事务边界

一轮聊天天然是一个业务单元。以前 user 消息和 assistant 消息分两次提交，极端情况下可能出现只写入半轮。现在两条消息在一个事务里写入，数据一致性更好。

### 避免私有依赖穿透

`vector_store` 之前直接依赖 `services.memory._connect`，这是一种跨层穿透。现在向量记录读写交给 `vector_repository`，模块之间的依赖方向更干净。

## 验证结果

已执行：

```bash
python -B -m py_compile Echo-backend\db\connection.py Echo-backend\db\schema.py Echo-backend\repositories\user_repository.py Echo-backend\repositories\conversation_repository.py Echo-backend\repositories\message_repository.py Echo-backend\repositories\memory_repository.py Echo-backend\repositories\vector_repository.py Echo-backend\services\memory.py Echo-backend\services\chat.py Echo-backend\services\vector_store.py Echo-backend\tests\test_repositories.py
```

结果：通过。

已执行：

```bash
python -B -m unittest discover -s Echo-backend\tests
```

结果：

```text
Ran 11 tests
OK
```

已执行应用装配检查：

```bash
python -B -c "import sys; sys.path.insert(0, 'Echo-backend'); import main; print(len(main.app.routes))"
```

结果：

```text
14
```

## 后续建议

第三轮建议处理后台任务和外部供应商适配：

- 把长期记忆抽取从 `asyncio.create_task` 迁移到可恢复任务表或轻量任务队列
- 抽出 `LLMProvider`、`EmbeddingProvider`、`ASRProvider`、`TTSProvider`
- 让 service 层只依赖 provider 接口，不直接依赖具体供应商 SDK
- 为任务执行增加状态、重试次数、失败原因和幂等键
