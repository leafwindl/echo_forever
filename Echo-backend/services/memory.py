import sqlite3
import uuid
from typing import Dict, List, Optional

DB_PATH = "echo_memory.db"


def _connect():
    """统一创建 SQLite 连接，后续如果迁移到 PostgreSQL，可以先从这里开始替换。"""
    return sqlite3.connect(DB_PATH)


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """检查旧表里是否已有某个字段，用于做非破坏性迁移。"""
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column_if_missing(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
    """只在字段缺失时 ALTER TABLE，避免重复启动服务时报错。"""
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """初始化数据库，并执行不会删除旧数据的表结构迁移。"""
    with _connect() as conn:
        cursor = conn.cursor()

        # 用户表：后续所有聊天记录、会话和长期记忆都必须按 user_id 隔离。
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                openid TEXT UNIQUE,
                nickname TEXT,
                avatar_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 会话表：v0.2 后续阶段会在这里保存 conversation_id 和滚动摘要 summary。
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                title TEXT,
                summary TEXT DEFAULT '',
                summary_message_id INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _add_column_if_missing(cursor, "conversations", "summary_message_id", "INTEGER DEFAULT 0")

        # 原始消息表：继续兼容 v0.1 的聊天历史，同时预留会话和消息类型字段。
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                conversation_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # 兼容已经存在的旧数据库：只补字段，不重建表，避免历史聊天记录丢失。
        _add_column_if_missing(cursor, "chat_messages", "conversation_id", "TEXT")
        _add_column_if_missing(cursor, "chat_messages", "message_type", "TEXT DEFAULT 'text'")

        # 长期记忆表：第一阶段只建表，真正的抽取/更新逻辑会在后续阶段接入。
        cursor.execute(
            """
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
            )
            """
        )

        # 常用查询索引：主要服务于按用户隔离读取历史、会话和长期记忆。
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_openid ON users(openid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_user_conversation_id
            ON chat_messages(user_id, conversation_id, id)
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_memories_user_status
            ON user_memories(user_id, status)
            """
        )
        conn.commit()


def upsert_user(
    user_id: str,
    openid: Optional[str] = None,
    nickname: Optional[str] = None,
    avatar_url: Optional[str] = None,
):
    """创建或更新用户资料，但不改变已经生成的稳定 user_id。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (user_id, openid, nickname, avatar_url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                openid = COALESCE(excluded.openid, users.openid),
                nickname = COALESCE(excluded.nickname, users.nickname),
                avatar_url = COALESCE(excluded.avatar_url, users.avatar_url),
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, openid, nickname, avatar_url),
        )
        conn.commit()


def ensure_conversation(user_id: str, conversation_id: Optional[str] = None, title: Optional[str] = None) -> str:
    """确保会话存在；调用方没传 conversation_id 时，创建一个新的会话 ID。"""
    upsert_user(user_id=user_id)
    resolved_id = conversation_id or f"conv_{uuid.uuid4().hex}"
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO conversations (conversation_id, user_id, title)
            VALUES (?, ?, ?)
            """,
            (resolved_id, user_id, title),
        )
        conn.commit()
    return resolved_id


def get_or_create_active_conversation(user_id: str) -> str:
    """获取用户当前 active 会话；不存在时自动创建一个。"""
    upsert_user(user_id=user_id)
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT conversation_id
            FROM conversations
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()

    if row:
        conversation_id = row[0]
    else:
        conversation_id = ensure_conversation(user_id)

    # 兼容历史数据：v0.2 早期消息可能没有 conversation_id。
    # 首次进入会话体系时，把这些旧消息挂到当前 active 会话下，避免短期历史突然断掉。
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE chat_messages
            SET conversation_id = ?
            WHERE user_id = ? AND conversation_id IS NULL
            """,
            (conversation_id, user_id),
        )
        conn.commit()

    return conversation_id


def get_conversation_summary(user_id: str, conversation_id: str) -> Dict[str, object]:
    """读取会话摘要和摘要已经覆盖到的消息 ID。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT summary, COALESCE(summary_message_id, 0)
            FROM conversations
            WHERE user_id = ? AND conversation_id = ?
            """,
            (user_id, conversation_id),
        )
        row = cursor.fetchone()

    if not row:
        return {"summary": "", "summary_message_id": 0}

    return {"summary": row[0] or "", "summary_message_id": int(row[1] or 0)}


def update_conversation_summary(
    user_id: str,
    conversation_id: str,
    summary: str,
    summary_message_id: int,
):
    """更新会话滚动摘要。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE conversations
            SET summary = ?,
                summary_message_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND conversation_id = ?
            """,
            (summary, summary_message_id, user_id, conversation_id),
        )
        conn.commit()


def add_message(
    user_id: str,
    role: str,
    content: str,
    conversation_id: Optional[str] = None,
    message_type: str = "text",
) -> int:
    """写入一条原始聊天消息，并返回数据库行 ID。"""
    # 兜底保护：即使某些开发路径绕过 /login 直接发消息，也先补齐 users 表记录。
    upsert_user(user_id=user_id)
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_messages (user_id, conversation_id, role, content, message_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, conversation_id, role, content, message_type),
        )
        if conversation_id:
            cursor.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND conversation_id = ?
                """,
                (user_id, conversation_id),
            )
        conn.commit()
        return int(cursor.lastrowid)


def get_history(
    user_id: str,
    limit: int = 20,
    conversation_id: Optional[str] = None,
    after_message_id: int = 0,
) -> List[Dict[str, str]]:
    """读取最近 N 条历史消息，并按时间正序返回给大模型。"""
    with _connect() as conn:
        cursor = conn.cursor()
        if conversation_id:
            cursor.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = ? AND conversation_id = ? AND id > ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, conversation_id, after_message_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = ? AND id > ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, after_message_id, limit),
            )
        rows = cursor.fetchall()

    # SQL 查询为了性能先取倒序的最新 N 条，这里反转回自然对话顺序。
    rows.reverse()
    return [{"role": row[0], "content": row[1]} for row in rows]


def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    after_message_id: int = 0,
) -> List[Dict[str, object]]:
    """按时间正序读取一个会话的所有原始消息，供摘要服务使用。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, role, content, message_type, timestamp
            FROM chat_messages
            WHERE user_id = ? AND conversation_id = ? AND id > ?
            ORDER BY id ASC
            """,
            (user_id, conversation_id, after_message_id),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": int(row[0]),
            "role": row[1],
            "content": row[2],
            "message_type": row[3],
            "timestamp": row[4],
        }
        for row in rows
    ]


def add_user_memory(
    user_id: str,
    memory_type: str,
    content: str,
    source_message_id: Optional[int] = None,
    confidence: float = 0.8,
    importance: int = 3,
) -> str:
    """写入一条结构化长期记忆；记忆抽取和去重逻辑会在后续阶段接入。"""
    memory_id = f"mem_{uuid.uuid4().hex}"
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_memories (
                memory_id, user_id, memory_type, content,
                source_message_id, confidence, importance
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (memory_id, user_id, memory_type, content, source_message_id, confidence, importance),
        )
        conn.commit()
    return memory_id
