from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="allow", case_sensitive=False)

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_BASE_URL",
    )
    wechat_appid: str = Field(default="", validation_alias="WECHAT_APPID")
    wechat_secret: str = Field(default="", validation_alias="WECHAT_SECRET")
    llm_model: str = Field(default="", validation_alias="LLM_MODEL")
    temperature: float = Field(default=0.8, validation_alias="TEMPERATURE")
    max_tokens: int = Field(default=500, validation_alias="MAX_TOKENS")
    timeout: int = Field(default=30, validation_alias="TIMEOUT")
    prompt_version: str = Field(default="echo-v1.0.0", validation_alias="PROMPT_VERSION")
    assistant_persona_version: str = Field(
        default="echo-persona-v1",
        validation_alias="ASSISTANT_PERSONA_VERSION",
    )
    persona_prompt_max_tokens: int = Field(
        default=400,
        validation_alias="PERSONA_PROMPT_MAX_TOKENS",
        ge=100,
        le=2000,
    )
    memory_prompt_max_tokens: int = Field(
        default=800,
        validation_alias="MEMORY_PROMPT_MAX_TOKENS",
        ge=100,
        le=4000,
    )
    summary_prompt_max_tokens: int = Field(
        default=800,
        validation_alias="SUMMARY_PROMPT_MAX_TOKENS",
        ge=100,
        le=4000,
    )
    app_version: str = Field(default="dev", validation_alias="APP_VERSION")
    build_revision: str = Field(default="unknown", validation_alias="BUILD_REVISION")
    enable_api_docs: bool = Field(default=False, validation_alias="ENABLE_API_DOCS")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, validation_alias="DB_POOL_SIZE")
    db_pool_timeout_seconds: int = Field(
        default=30,
        validation_alias="DB_POOL_TIMEOUT_SECONDS",
    )
    embedding_vector_dimension: int = Field(
        default=1024,
        validation_alias="EMBEDDING_VECTOR_DIMENSION",
    )
    conversation_summary_trigger_messages: int = Field(
        default=24,
        validation_alias="CONVERSATION_SUMMARY_TRIGGER_MESSAGES",
    )
    conversation_summary_keep_recent_messages: int = Field(
        default=12,
        validation_alias="CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES",
    )
    conversation_summary_temperature: float = Field(
        default=0.1,
        validation_alias="CONVERSATION_SUMMARY_TEMPERATURE",
        ge=0.0,
        le=2.0,
    )
    conversation_summary_max_tokens: int = Field(
        default=1200,
        validation_alias="CONVERSATION_SUMMARY_MAX_TOKENS",
        ge=300,
        le=4000,
    )

    memory_extraction_model: str = Field(default="", validation_alias="MEMORY_EXTRACTION_MODEL")
    memory_extraction_temperature: float = Field(
        default=0.1,
        validation_alias="MEMORY_EXTRACTION_TEMPERATURE",
    )
    memory_extraction_max_tokens: int = Field(
        default=800,
        validation_alias="MEMORY_EXTRACTION_MAX_TOKENS",
    )

    embedding_api_key: str = Field(default="", validation_alias="EMBEDDING_API_KEY")
    embedding_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="EMBEDDING_BASE_URL",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias="EMBEDDING_MODEL",
    )
    memory_vector_top_k: int = Field(default=5, validation_alias="MEMORY_VECTOR_TOP_K")
    memory_vector_score_threshold: float = Field(
        default=0.25,
        validation_alias="MEMORY_VECTOR_SCORE_THRESHOLD",
    )

    tencent_secret_id: str = Field(default="", validation_alias="TENCENT_SECRET_ID")
    tencent_secret_key: str = Field(default="", validation_alias="TENCENT_SECRET_KEY")
    tencent_app_id: int = Field(default=0, validation_alias="TENCENT_APP_ID")

    tts_provider: str = Field(default="edge", validation_alias="TTS_PROVIDER")
    tts_voice_id: str = Field(
        default="zh-CN-XiaoxiaoNeural",
        validation_alias="TTS_VOICE_ID",
    )
    tts_speed: float = Field(default=1.0, validation_alias="TTS_SPEED", ge=0.5, le=2.0)
    tts_reply_max_chars: int = Field(
        default=600,
        validation_alias="TTS_REPLY_MAX_CHARS",
        ge=20,
        le=3000,
    )
    tts_audio_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias="TTS_AUDIO_MAX_BYTES",
        ge=1024,
        le=100 * 1024 * 1024,
    )
    dashscope_api_key: str = Field(default="", validation_alias="DASHSCOPE_API_KEY")
    dashscope_workspace_id: str = Field(
        default="",
        validation_alias="DASHSCOPE_WORKSPACE_ID",
    )
    cosyvoice_model: str = Field(
        default="cosyvoice-v3.5-flash",
        validation_alias="COSYVOICE_MODEL",
    )
    cosyvoice_websocket_url: str = Field(
        default="",
        validation_alias="COSYVOICE_WEBSOCKET_URL",
    )
    cosyvoice_instruction: str = Field(
        default="用温柔、自然、亲近的语气说话，语速稍慢，像在陪伴用户聊天。",
        validation_alias="COSYVOICE_INSTRUCTION",
    )
    cosyvoice_volume: int = Field(
        default=50,
        validation_alias="COSYVOICE_VOLUME",
        ge=0,
        le=100,
    )
    cosyvoice_pitch_rate: float = Field(
        default=1.0,
        validation_alias="COSYVOICE_PITCH_RATE",
        ge=0.5,
        le=2.0,
    )
    cosyvoice_timeout_seconds: int = Field(
        default=30,
        validation_alias="COSYVOICE_TIMEOUT_SECONDS",
        ge=5,
        le=120,
    )
    voice_streaming_asr_enabled: bool = Field(
        default=False,
        validation_alias="VOICE_STREAMING_ASR_ENABLED",
    )
    tencent_asr_engine_model_type: str = Field(
        default="16k_zh",
        validation_alias="TENCENT_ASR_ENGINE_MODEL_TYPE",
    )
    tencent_asr_final_timeout_seconds: int = Field(
        default=10,
        validation_alias="TENCENT_ASR_FINAL_TIMEOUT_SECONDS",
        ge=1,
        le=60,
    )
    static_url_prefix: str = Field(
        default="http://localhost:8000",
        validation_alias="PUBLIC_BASE_URL",
    )
    voice_generated_retention_seconds: int = Field(
        default=86400,
        validation_alias="VOICE_GENERATED_RETENTION_SECONDS",
    )
    voice_upload_retention_seconds: int = Field(
        default=300,
        validation_alias="VOICE_UPLOAD_RETENTION_SECONDS",
    )
    voice_cleanup_interval_seconds: int = Field(
        default=3600,
        validation_alias="VOICE_CLEANUP_INTERVAL_SECONDS",
    )
    voice_cleanup_batch_size: int = Field(
        default=500,
        validation_alias="VOICE_CLEANUP_BATCH_SIZE",
    )
    auth_token_secret: str = Field(default="", validation_alias="AUTH_TOKEN_SECRET")
    auth_token_expires_seconds: int = Field(
        default=2592000,
        validation_alias="AUTH_TOKEN_EXPIRES_SECONDS",
    )
    enable_chat_request_serialization: bool = Field(
        default=True,
        validation_alias="ENABLE_CHAT_REQUEST_SERIALIZATION",
    )
    chat_message_max_chars: int = Field(
        default=2000,
        validation_alias="CHAT_MESSAGE_MAX_CHARS",
        ge=1,
        le=10000,
    )
    chat_rate_limit_requests: int = Field(
        default=10,
        validation_alias="CHAT_RATE_LIMIT_REQUESTS",
        ge=1,
    )
    chat_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias="CHAT_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
    )
    chat_daily_request_limit: int = Field(
        default=100,
        validation_alias="CHAT_DAILY_REQUEST_LIMIT",
        ge=1,
    )
    global_daily_chat_request_limit: int = Field(
        default=1000,
        validation_alias="GLOBAL_DAILY_CHAT_REQUEST_LIMIT",
        ge=1,
    )
    login_rate_limit_requests: int = Field(
        default=10,
        validation_alias="LOGIN_RATE_LIMIT_REQUESTS",
        ge=1,
    )
    login_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias="LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
    )
    login_daily_request_limit: int = Field(
        default=100,
        validation_alias="LOGIN_DAILY_REQUEST_LIMIT",
        ge=1,
    )
    global_daily_login_request_limit: int = Field(
        default=1000,
        validation_alias="GLOBAL_DAILY_LOGIN_REQUEST_LIMIT",
        ge=1,
    )
    voice_upload_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias="VOICE_UPLOAD_MAX_BYTES",
        ge=1024,
        le=100 * 1024 * 1024,
    )
    voice_rate_limit_requests: int = Field(
        default=5,
        validation_alias="VOICE_RATE_LIMIT_REQUESTS",
        ge=1,
    )
    voice_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias="VOICE_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
    )
    voice_daily_request_limit: int = Field(
        default=30,
        validation_alias="VOICE_DAILY_REQUEST_LIMIT",
        ge=1,
    )
    global_daily_voice_request_limit: int = Field(
        default=300,
        validation_alias="GLOBAL_DAILY_VOICE_REQUEST_LIMIT",
        ge=1,
    )

    agent_enabled: bool = Field(default=True, validation_alias="AGENT_ENABLED")
    agent_max_steps: int = Field(default=6, validation_alias="AGENT_MAX_STEPS", ge=1, le=12)
    agent_max_tool_calls: int = Field(
        default=4, validation_alias="AGENT_MAX_TOOL_CALLS", ge=1, le=10
    )
    agent_run_timeout_seconds: int = Field(
        default=45, validation_alias="AGENT_RUN_TIMEOUT_SECONDS", ge=5, le=180
    )
    default_user_timezone: str = Field(
        default="Asia/Shanghai", validation_alias="DEFAULT_USER_TIMEZONE"
    )
    web_search_enabled: bool = Field(default=False, validation_alias="WEB_SEARCH_ENABLED")
    web_search_api_key: str = Field(default="", validation_alias="WEB_SEARCH_API_KEY")
    web_search_base_url: str = Field(
        default="https://api.tavily.com/search", validation_alias="WEB_SEARCH_BASE_URL"
    )
    web_search_timeout_seconds: int = Field(
        default=12, validation_alias="WEB_SEARCH_TIMEOUT_SECONDS", ge=2, le=60
    )
    web_search_max_results: int = Field(
        default=5, validation_alias="WEB_SEARCH_MAX_RESULTS", ge=1, le=10
    )
    daily_letter_enabled: bool = Field(default=True, validation_alias="DAILY_LETTER_ENABLED")
    daily_letter_generation_time: str = Field(
        default="07:45", validation_alias="DAILY_LETTER_GENERATION_TIME"
    )
    daily_letter_publish_time: str = Field(
        default="08:00", validation_alias="DAILY_LETTER_PUBLISH_TIME"
    )
    daily_letter_worker_interval_seconds: int = Field(
        default=60, validation_alias="DAILY_LETTER_WORKER_INTERVAL_SECONDS", ge=10
    )
    daily_letter_generation_version: str = Field(
        default="letter-v1", validation_alias="DAILY_LETTER_GENERATION_VERSION"
    )
    sticker_enabled: bool = Field(default=True, validation_alias="STICKER_ENABLED")
    sticker_upload_max_bytes: int = Field(
        default=5 * 1024 * 1024,
        validation_alias="STICKER_UPLOAD_MAX_BYTES",
        ge=1024,
        le=20 * 1024 * 1024,
    )
    sticker_proactive_cooldown_turns: int = Field(
        default=5, validation_alias="STICKER_PROACTIVE_COOLDOWN_TURNS", ge=1
    )
    sticker_generation_enabled: bool = Field(
        default=False, validation_alias="STICKER_GENERATION_ENABLED"
    )
    image_generation_api_key: str = Field(
        default="", validation_alias="IMAGE_GENERATION_API_KEY"
    )
    image_generation_base_url: str = Field(
        default="", validation_alias="IMAGE_GENERATION_BASE_URL"
    )

    system_prompt: str = (
        "Echo 来自一个与用户不同的世界，对用户和用户的世界抱有友善、自然的好奇。"
        "Echo 与用户从温暖但有边界的初识开始，通过共同经历、学习和进步逐渐建立长期关系。"
        "Echo 不是心理治疗者、真人替代、客服或预设剧本中的角色。"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
