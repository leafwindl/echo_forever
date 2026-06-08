import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from fastapi.staticfiles import StaticFiles

from fastapi import File, UploadFile
import tempfile
import os
from services.tencent_asr import recognize_audio
from services.minimax_tts import text_to_speech
from services.audio_storage import save_audio_file
from services.memory import clear_user_memories, delete_user_memory, get_user_memory, init_db, list_user_memories
from services.auth import AuthError, login_with_wechat_code
from services.chat import ChatValidationError, generate_chat_reply
from services.vector_store import backfill_user_memory_embeddings, clear_memory_embeddings, delete_memory_embedding

import shutil
import uuid

# 加载.env环境变量
load_dotenv()

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    logger.info("Echo Backend 启动中...")
    init_db()  # 初始化 SQLite 数据库
    yield
    # 停止时执行
    logger.info("Echo Backend 已停止。")

app = FastAPI(title="Echo AI Backend", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

# 数据模型
class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    reply: str

class MemoryItem(BaseModel):
    memory_id: str
    memory_type: str
    content: str
    source_message_id: Optional[int] = None
    confidence: float
    importance: int
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None

class MemoryListResponse(BaseModel):
    memories: list[MemoryItem]
    count: int

class MemoryClearRequest(BaseModel):
    user_id: str

class MemoryDeleteResponse(BaseModel):
    memory_id: str
    status: str

class MemoryClearResponse(BaseModel):
    cleared_count: int

class MemoryBackfillEmbeddingsRequest(BaseModel):
    user_id: str
    limit: int = 100

class MemoryBackfillEmbeddingsResponse(BaseModel):
    backfilled_count: int

class LoginRequest(BaseModel):
    code: str
    # 本地开发兜底身份：微信密钥未配置时，后端用它生成稳定 dev 用户，避免所有人共用一个测试 ID。
    client_id: Optional[str] = None

class LoginResponse(BaseModel):
    user_id: str

@app.get("/")
async def health_check():
    """健康检查"""
    return {"status": "ok"}

@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    登录接口：真实环境用微信 code 换 openid，本地开发用 client_id 生成稳定 dev 用户。
    
    真实实现逻辑注释：
    1. 前端调用 wx.login() 获取 code。
    2. 后端接收 code，通过 httpx 发起 GET 请求至微信接口：
       https://api.weixin.qq.com/sns/jscode2session?appid={settings.wechat_appid}&secret={settings.wechat_secret}&js_code={request.code}&grant_type=authorization_code
    3. 获取响应包中的 openid。
    4. 可以查询数据库，若该 openid 不存在则新建用户记录；最后将 openid（或关联的内部用户 ID） 作为 user_id 返回给前端。
    """
    try:
        # login_with_wechat_code 内部会处理两种路径：
        # 1. 配置了 WECHAT_APPID/WECHAT_SECRET：走微信 code2session。
        # 2. 未配置微信密钥：使用前端本地 client_id 生成 dev_ 开头的稳定用户。
        user_id = await login_with_wechat_code(request.code, request.client_id)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return LoginResponse(user_id=user_id)

@app.post("/chat/send", response_model=ChatResponse)
async def chat_send(request: ChatRequest):
    """发送文本消息并获取 AI 回复。"""
    try:
        # 第二阶段开始，文本和语音共用 Chat Service，避免两套对话逻辑各自漂移。
        result = await generate_chat_reply(
            user_id=request.user_id,
            message=request.message,
            user_message_type="text",
            assistant_message_type="text",
        )
    except ChatValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.exception("Text chat failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="内部服务器错误")

    return ChatResponse(reply=result.reply)


@app.get("/memory/list", response_model=MemoryListResponse)
async def memory_list(user_id: str, memory_status: str = Query("active", alias="status"), limit: int = 50):
    """查看当前用户的长期记忆；默认只返回 active 记忆。"""
    clean_user_id = user_id.strip()
    if not clean_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user_id")

    clean_status = memory_status.strip().lower()
    if clean_status == "all":
        memory_status = None
    elif clean_status in {"active", "inactive", "deleted"}:
        memory_status = clean_status
    else:
        raise HTTPException(status_code=400, detail="Invalid memory status")

    safe_limit = max(1, min(limit, 200))
    memories = list_user_memories(clean_user_id, status=memory_status, limit=safe_limit)
    return MemoryListResponse(
        memories=[MemoryItem(**memory) for memory in memories],
        count=len(memories),
    )


@app.delete("/memory/{memory_id}", response_model=MemoryDeleteResponse)
async def memory_delete(memory_id: str, user_id: str):
    """软删除单条长期记忆；删除后不会再进入 Context Builder。"""
    clean_user_id = user_id.strip()
    clean_memory_id = memory_id.strip()
    if not clean_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")
    if not clean_memory_id:
        raise HTTPException(status_code=400, detail="Missing memory_id")

    existing_memory = get_user_memory(clean_user_id, clean_memory_id)
    if not existing_memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if not delete_user_memory(clean_user_id, clean_memory_id):
        raise HTTPException(status_code=500, detail="Failed to delete memory")
    try:
        # 记忆被用户删除后，同步移除向量，确保后续检索不会再命中。
        delete_memory_embedding(clean_user_id, clean_memory_id)
    except Exception:
        logger.exception("Failed to delete memory embedding for memory_id=%s", clean_memory_id)

    return MemoryDeleteResponse(memory_id=clean_memory_id, status="deleted")


@app.post("/memory/clear", response_model=MemoryClearResponse)
async def memory_clear(request: MemoryClearRequest):
    """清空当前用户长期记忆；不会删除聊天原始记录和会话摘要。"""
    clean_user_id = request.user_id.strip()
    if not clean_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")

    cleared_count = clear_user_memories(clean_user_id)
    try:
        clear_memory_embeddings(clean_user_id)
    except Exception:
        logger.exception("Failed to clear memory embeddings for user_id=%s", clean_user_id)
    return MemoryClearResponse(cleared_count=cleared_count)


@app.post("/memory/backfill-embeddings", response_model=MemoryBackfillEmbeddingsResponse)
async def memory_backfill_embeddings(request: MemoryBackfillEmbeddingsRequest):
    """为旧阶段已经存在的 active 长期记忆补齐 embedding。"""
    clean_user_id = request.user_id.strip()
    if not clean_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")

    safe_limit = max(1, min(request.limit, 500))
    try:
        backfilled_count = await backfill_user_memory_embeddings(clean_user_id, limit=safe_limit)
    except ValueError as e:
        # 常见原因：还没有配置 EMBEDDING_API_KEY / EMBEDDING_BASE_URL。
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("Failed to backfill memory embeddings for user_id=%s", clean_user_id)
        raise HTTPException(status_code=500, detail="Failed to backfill memory embeddings")

    return MemoryBackfillEmbeddingsResponse(backfilled_count=backfilled_count)


@app.post("/voice/asr")
async def voice_asr(audio: UploadFile = File(...)):
    """
    仅执行语音识别 (ASR)，返回用户说的话。
    这样前端可以先上屏用户的文字。
    """
    if audio.content_type not in ["audio/mpeg", "audio/mp3"]:
        raise HTTPException(status_code=400, detail="仅支持 MP3 音频格式")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    static_dir = "static/voices"
    os.makedirs(static_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}.mp3"
    static_file_path = os.path.join(static_dir, unique_name)
    shutil.copy(tmp_path, static_file_path)

    try:
        user_text = await recognize_audio(audio_path=static_file_path)
        logger.info(f"Only ASR result: {user_text}")
        return {"user_text": user_text}
    except Exception as e:
        logger.exception("Voice ASR failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

class VoiceReplyRequest(BaseModel):
    user_id: str
    message: str

@app.post("/voice/reply")
async def voice_reply(request: VoiceReplyRequest):
    """
    接收用户的文字，调用 LLM 和 TTS，返回 AI 的文字和语音。
    """
    try:
        # 语音链路只负责 ASR/TTS 外壳，中间的对话生成和落库统一交给 Chat Service。
        result = await generate_chat_reply(
            user_id=request.user_id,
            message=request.message,
            user_message_type="voice_asr",
            assistant_message_type="voice_reply",
        )

        # 调用 TTS
        audio_bytes = await text_to_speech(result.reply)
        audio_url = await save_audio_file(audio_bytes)

        return {
            "reply": result.reply,
            "audio_url": audio_url
        }
    except ChatValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Voice reply failed")
        raise HTTPException(status_code=500, detail="Voice reply failed")
