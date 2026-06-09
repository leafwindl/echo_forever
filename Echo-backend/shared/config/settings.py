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

    memory_extraction_model: str = Field(default="", validation_alias="MEMORY_EXTRACTION_MODEL")
    memory_extraction_temperature: float = Field(
        default=0.1,
        validation_alias="MEMORY_EXTRACTION_TEMPERATURE",
    )
    memory_extraction_max_tokens: int = Field(
        default=400,
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

    minimax_api_key: str = Field(default="", validation_alias="MINIMAX_API_KEY")
    minimax_group_id: str = Field(default="", validation_alias="MINIMAX_GROUP_ID")
    minimax_tts_voice_id: str = Field(
        default="zh-CN-XiaoxiaoNeural",
        validation_alias="MINIMAX_TTS_VOICE_ID",
    )

    static_url_prefix: str = Field(
        default="http://localhost:8000",
        validation_alias="PUBLIC_BASE_URL",
    )

    system_prompt: str = (
        "你叫Echo，一位温柔、细腻的AI伙伴。\n"
        "你总是用自然、不生硬的方式回复，像好朋友一样。\n"
        "回答简洁但有温度，可以适当表达关心。\n"
        "用户说什么，你都耐心倾听，并给予支持。"
    )

    @property
    def LLM_MODEL(self) -> str:
        """Compatibility alias for older code that still reads settings.LLM_MODEL."""
        return self.llm_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
