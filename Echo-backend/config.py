import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """项目配置类"""
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    wechat_appid: str = os.getenv("WECHAT_APPID", "")
    wechat_secret: str = os.getenv("WECHAT_SECRET", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    temperature: float = 0.8
    max_tokens: int = 500
    timeout: int = 30
    memory_extraction_model: str = os.getenv("MEMORY_EXTRACTION_MODEL", "")
    memory_extraction_temperature: float = float(os.getenv("MEMORY_EXTRACTION_TEMPERATURE", "0.1"))
    memory_extraction_max_tokens: int = int(os.getenv("MEMORY_EXTRACTION_MAX_TOKENS", "400"))
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_base_url: str = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    memory_vector_top_k: int = int(os.getenv("MEMORY_VECTOR_TOP_K", "5"))
    memory_vector_score_threshold: float = float(os.getenv("MEMORY_VECTOR_SCORE_THRESHOLD", "0.25"))

    # ASR服务
    tencent_secret_id: str = os.getenv("TENCENT_SECRET_ID", "")
    tencent_secret_key: str = os.getenv("TENCENT_SECRET_KEY", "")
    tencent_app_id: int = int(os.getenv("TENCENT_APP_ID", 0))

    # TTS服务
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_group_id: str = os.getenv("MINIMAX_GROUP_ID", "")
    minimax_tts_voice_id: str = os.getenv("MINIMAX_TTS_VOICE_ID", "male-qn-qingse")  # 一个默认音色

    # 静态文件服务URL前缀（用于返回给前端或提供给腾讯云作为下载源）
    static_url_prefix: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    
    # 系统 Prompt
    system_prompt: str = (
        "你叫Echo，一位温柔、细腻的AI伙伴。\n"
        "你总是用自然、不生硬的方式回复，像好朋友一样。\n"
        "回答简洁但有温度，可以适当表达关心。\n"
        "用户说什么，你都耐心倾听，并给予支持。"
    )

    class Config:
        env_file = ".env",
        extra = "allow"  # 添加这一行即可

settings = Settings()
