# Echo 后端第十轮数据库迁移与备份说明

## 1. 本轮目标

本轮将 Echo 的运行数据库从 SQLite 完整迁移到 PostgreSQL + pgvector，并补齐自动备份能力。

目标包括：

- 业务运行时只使用 PostgreSQL。
- 长期记忆向量收敛到 pgvector。
- 保持 Application、Domain 不依赖具体数据库。
- 提供一次性的 SQLite 历史数据迁移工具。
- 提供独立于业务进程的 PostgreSQL 自动备份与恢复工具。
- 删除 SQLite 运行兼容路径，避免长期维护双数据库实现。

## 2. 改了什么

### 2.1 PostgreSQL 运行基础设施

新增：

- `db/postgres_connection.py`：管理 PostgreSQL 连接与事务。
- `db/postgres_schema.py`：定义 PostgreSQL 表、索引和 pgvector 字段。
- `features/auth/infrastructure/postgres_repositories.py`：用户数据实现。
- `features/chat/infrastructure/postgres_repositories.py`：会话和消息实现。
- `features/memory/infrastructure/postgres_repositories.py`：长期记忆、向量和后台任务实现。

`db/schema.py` 负责应用启动时初始化 PostgreSQL schema，默认向量维度为 1024。

### 2.2 数据库选择与装配

配置默认值调整为：

```dotenv
DB_PROVIDER=postgres
DATABASE_URL=postgresql://...
EMBEDDING_VECTOR_DIMENSION=1024
```

各 Feature 的 Infrastructure 通过 `repository_provider.py` 装配 PostgreSQL repository。Interface、Application 和 Domain 不读取数据库连接配置，也不直接导入 psycopg。

### 2.3 SQLite 历史数据迁移

新增：

```text
scripts/migrate_sqlite_to_postgres.py
```

迁移内容包括：

- 用户
- 会话
- 聊天消息
- 长期记忆
- 长期记忆向量
- 后台任务
- 运行时配置
- 已存在时的语音文件记录

迁移脚本会建立旧 SQLite 消息 ID 到 PostgreSQL 消息 ID 的映射，保证会话摘要边界和长期记忆来源引用不会错位。

迁移使用可重复执行的 upsert；但正式切换时仍应停止旧后端写入，只执行一次最终迁移并完成验证。

### 2.4 删除 SQLite 运行兼容

已删除：

- SQLite connection 和 schema 初始化代码。
- Auth、Chat、Memory 的 SQLite repository。
- SQLite 专用运行测试。
- SQLite 备份与恢复脚本。

SQLite 文件现在只是一次性迁移输入，不再参与业务运行。

### 2.5 PostgreSQL 自动备份

新增 Compose 服务：

```text
echo-postgres-backup
```

新增脚本：

```text
scripts/postgres_backup.sh
scripts/postgres_restore.sh
```

自动备份行为：

1. 备份容器等待 PostgreSQL 健康。
2. 容器启动后立即执行一次 `pg_dump`。
3. 默认每 86400 秒执行一次。
4. 使用 PostgreSQL custom dump 格式。
5. 临时文件通过 `pg_restore --list` 校验后才改为正式文件名。
6. 默认清理超过 7 天的备份。
7. 备份写入宿主机 `data/backups/postgres/`。

## 3. 有什么用

### 3.1 PostgreSQL

- 支持更高的并发读写和更明确的事务语义。
- 为后续索引、数据生命周期、异步任务和多实例部署提供基础。
- 数据不再依赖单个 SQLite 文件锁。

### 3.2 pgvector

- 长期记忆及其向量位于同一个数据库事务和用户边界内。
- 可以按 `user_id` 和 embedding 模型过滤后做相似度检索。
- pgvector 负责向量存储与检索，Embedding API 仍负责把文本转换为向量。

### 3.3 自动备份

- 防止误删记录、数据库损坏或误删 volume 后完全无法恢复。
- 备份与 FastAPI 生命周期解耦，业务异常不会改变备份逻辑。
- 备份文件位于 Docker volume 之外，便于复制到 COS 或其它机器。

## 4. 边界说明

### 4.1 业务架构边界

```text
Interface
  -> Application
    -> Domain Repository Protocol
      <- Infrastructure PostgreSQL Repository
        -> db/postgres_connection.py
```

- Interface：只负责 HTTP 参数、鉴权和响应格式。
- Application：编排聊天、记忆等业务流程。
- Domain：定义实体、值对象和 Repository 抽象。
- Infrastructure：实现 PostgreSQL、pgvector和第三方服务访问。
- `db/`：只提供连接、事务和 schema，不承载业务规则。

### 4.2 运维边界

```text
FastAPI 业务容器       -> 读取和写入 PostgreSQL
PostgreSQL 容器        -> 保存在线数据
备份容器               -> 定时只读 pg_dump
宿主机备份目录         -> 保存 dump 文件
SQLite 迁移脚本        -> 只在历史数据迁移时执行
```

备份不由路由、Application 用例或后台记忆任务触发。恢复也不会通过 HTTP API 暴露，只允许运维人员在停止业务后显式执行。

### 4.3 配置边界

根目录 `.env`：

- Docker Compose PostgreSQL 用户和密码。
- 容器内部数据库连接地址。
- 自动备份间隔与保留天数。

`Echo-backend/.env`：

- 本地直跑后端时的数据库连接。
- LLM、Embedding、微信、鉴权、语音等业务配置。

`.env.compose.example` 和 `Echo-backend/.env.example` 只提供字段模板，不保存真实密码。

## 5. 怎么使用

### 5.1 本地启动

```powershell
docker compose up -d echo-postgres echo-postgres-backup
```

本地直接运行后端时：

```dotenv
DB_PROVIDER=postgres
DATABASE_URL=postgresql://echo:<password>@127.0.0.1:5432/echo
```

### 5.2 查看自动备份

```powershell
docker compose ps
docker compose logs -f echo-postgres-backup
Get-ChildItem data\backups\postgres
```

### 5.3 手工立即备份

```powershell
docker compose run --rm --entrypoint /bin/sh echo-postgres-backup `
  /scripts/postgres_backup.sh once
```

### 5.4 恢复备份

恢复会重建目标数据库，必须先停止业务和自动备份：

```powershell
docker compose stop echo-backend echo-postgres-backup
```

执行恢复：

```powershell
docker compose run --rm `
  -e CONFIRM_POSTGRES_RESTORE=echo `
  --entrypoint /bin/sh `
  echo-postgres-backup `
  /scripts/postgres_restore.sh /backups/<backup-file>.dump
```

恢复后重新启动并验证：

```powershell
docker compose up -d echo-postgres-backup echo-backend
docker compose logs -f echo-backend
```

### 5.5 修改备份策略

根目录 `.env`：

```dotenv
POSTGRES_BACKUP_INTERVAL_SECONDS=86400
POSTGRES_BACKUP_RETENTION_DAYS=7
```

修改后重建备份服务：

```powershell
docker compose up -d --force-recreate echo-postgres-backup
```

## 6. 验证结果

- SQLite 历史数据已在本地成功迁移到 PostgreSQL。
- 用户、会话、消息、记忆、向量和后台任务数量迁移正确。
- pgvector schema 与 1024 维向量测试通过。
- PostgreSQL datetime 到领域字符串的边界转换已修复。
- 后端架构检查通过。
- 后端全量单元测试通过。

## 7. 后续工作

- 将备份目录定期同步到腾讯云 COS，避免服务器硬盘损坏时备份一起丢失。
- 在服务器完成一次实际恢复演练，并记录恢复耗时和验证结果。
- 增加备份失败告警，而不是只依赖 Docker 日志。
- 后续引入 Alembic 管理增量 schema 迁移，避免长期依赖启动时 `CREATE TABLE IF NOT EXISTS`。
