import sqlite3
import os
from typing import List, Dict

DB_PATH = "echo_memory.db"

def init_db():
    """初始化 SQLite 数据库，并创建聊天记录表"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 创建索引以加速按用户和时间的查询
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON chat_messages(user_id)')
        conn.commit()

def add_message(user_id: str, role: str, content: str):
    """添加一条新消息到数据库"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)',
            (user_id, role, content)
        )
        conn.commit()

def get_history(user_id: str, limit: int = 20) -> List[Dict[str, str]]:
    """获取指定用户的最近 N 条聊天记录（按时间先后顺序排序）"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content 
            FROM chat_messages 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        
    # 查询出来的是按时间倒序（最新的在前），我们需要反转成先后顺序供大模型理解
    rows.reverse()
    return [{"role": row[0], "content": row[1]} for row in rows]

