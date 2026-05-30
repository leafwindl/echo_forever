import logging
from typing import Dict, List
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from contextlib import asynccontextmanager

from config import settings
from llm_client import request_llm
from dotenv import load_dotenv

from fastapi.staticfiles import StaticFiles

from fastapi import File, UploadFile
import tempfile
import os
from services.tencent_asr import recognize_audio
from services.minimax_tts import text_to_speech
from services.audio_storage import save_audio_file
from services.memory import init_db, add_message, get_history

import shutil
import uuid

# 加载.env环境变量
load_dotenv()

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 保持最多多少轮对话（1轮 = 用户1条 + AI 1条）
MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2

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

class LoginRequest(BaseModel):
    code: str

class LoginResponse(BaseModel):
    user_id: str

@app.get("/")
async def health_check():
    """健康检查"""
    return {"status": "ok"}

@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    登录接口（当前为阶段一，返回固定测试 user_id）
    
    真实实现逻辑注释：
    1. 前端调用 wx.login() 获取 code。
    2. 后端接收 code，通过 httpx 发起 GET 请求至微信接口：
       https://api.weixin.qq.com/sns/jscode2session?appid={settings.wechat_appid}&secret={settings.wechat_secret}&js_code={request.code}&grant_type=authorization_code
    3. 获取响应包中的 openid。
    4. 可以查询数据库，若该 openid 不存在则新建用户记录；最后将 openid（或关联的内部用户 ID） 作为 user_id 返回给前端。
    """
    return LoginResponse(user_id="test_user_001")

@app.post("/chat/send", response_model=ChatResponse)
async def chat_send(request: ChatRequest):
    """发送消息并获取 AI 回复"""
    # 获取前端发送过来的消息
    user_id = request.user_id
    user_message = request.message.strip()
    # 空消息校验
    if not user_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="空消息")

    # 获取用户持久化的历史记录（短期记忆）
    history = get_history(user_id, limit=MAX_HISTORY_MESSAGES)
    
    # 构造“本次”请求的完整消息列表（包含系统提示词+历史对话+当前用户消息），注意系统提示词是每次都会包含进去的
    messages = [{"role": "system", "content": settings.system_prompt}]
    # extend是将history的历史记录都追加在系统提示词的后面
    messages.extend(history)
    # 追加当前用户发来的消息
    messages.append({"role": "user", "content": user_message})
    
    try:
        reply_content = await request_llm(messages)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="内部服务器错误")
        
    # 持久化本次对话到数据库
    add_message(user_id, "user", user_message)
    add_message(user_id, "assistant", reply_content)
        
    return ChatResponse(reply=reply_content)


@app.post("/voice/chat")
async def voice_chat(audio: UploadFile = File(...), user_id: str = "test_user_001"):
    """
    接收前端上传的音频文件（MP3），完成 ASR -> LLM -> TTS -> 返回音频URL。
    当前 user_id 可以先固定为 test_user_001，后续可从前端请求参数中获取。
    """
    # 1. 校验文件类型
    if audio.content_type not in ["audio/mpeg", "audio/mp3"]:
        raise HTTPException(status_code=400, detail="仅支持 MP3 音频格式")

    # 2. 保存上传的音频到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    # 生成静态文件并获取公网 URL
    static_dir = "static/voices"
    os.makedirs(static_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}.mp3"
    static_file_path = os.path.join(static_dir, unique_name)
    shutil.copy(tmp_path, static_file_path)

    # 构建公网可访问的URL给腾讯云ASR
    public_url = f"{settings.static_url_prefix}/static/voices/{unique_name}"
    print(f"DEBUG: public_url is {public_url}")

    try:
        # 1. 语音转文字（ASR），现在安全地使用本地文件直接上传，避免 ngrok 访问警告页面的问题
        user_text = await recognize_audio(audio_path=static_file_path)
        logger.info(f"ASR result: {user_text}")

        # 2. 调用现有的大模型（复用 /chat/send 逻辑中的 LLM 调用）
        # 构造 messages（和 chat_send 中一致）
        messages = [{"role": "system", "content": settings.system_prompt}]
        # 注意：语音对话是否需要历史？根据需求决定。这里为了简单，不加载历史，实现单轮。
        # 若需要多轮历史，可以传入 user_id 并从 chat_history 中获取 history
        messages.append({"role": "user", "content": user_text})

        reply_text = await request_llm(messages)
        logger.info(f"LLM reply: {reply_text}")

        # 3. MiniMax TTS：文字 -> 音频二进制
        audio_bytes = await text_to_speech(reply_text)

        # 4. 保存音频并生成 URL
        audio_url = await save_audio_file(audio_bytes)

        # 5. (可选) 如果需要更新对话历史，可以像 chat_send 中那样操作 chat_history
        # 这里略，因为语音和文字历史应分开或合并？自行决定。MVP 可以先不存历史。

        return {
            "audio_url": audio_url, 
            "reply": reply_text, 
            "user_text": user_text
        }

    except Exception as e:
        logger.exception("Voice chat failed")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
    user_id = request.user_id
    user_text = request.message.strip()
    
    # 获取用户持久化的历史记录（短期记忆）
    history = get_history(user_id, limit=MAX_HISTORY_MESSAGES)
    
    messages = [{"role": "system", "content": settings.system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        reply_text = await request_llm(messages)
        logger.info(f"LLM reply for voice: {reply_text}")

        # 调用 TTS
        audio_bytes = await text_to_speech(reply_text)
        audio_url = await save_audio_file(audio_bytes)

        # 持久化本次对话到数据库
        add_message(user_id, "user", user_text)
        add_message(user_id, "assistant", reply_text)

        return {
            "reply": reply_text,
            "audio_url": audio_url
        }
    except Exception as e:
        logger.exception("Voice reply failed")
        raise HTTPException(status_code=500, detail="Voice reply failed")
