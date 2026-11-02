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
    llm_model: str = Field(default="", validation_alias="LLM_MODEL")
    temperature: float = Field(default=0.8, validation_alias="TEMPERATURE")
    max_tokens: int = Field(default=500, validation_alias="MAX_TOKENS")
    chat_max_tokens: int = Field(
        default=1800,
        validation_alias="CHAT_MAX_TOKENS",
        ge=200,
        le=8192,
    )
    call_max_tokens: int = Field(
        default=256,
        validation_alias="CALL_MAX_TOKENS",
        ge=64,
        le=1024,
    )
    call_history_messages: int = Field(
        default=8,
        validation_alias="CALL_HISTORY_MESSAGES",
        ge=2,
        le=20,
    )
    call_reply_max_chars: int = Field(
        default=80,
        validation_alias="CALL_REPLY_MAX_CHARS",
        ge=24,
        le=240,
    )
    call_tool_routing_enabled: bool = Field(
        default=False,
        validation_alias="CALL_TOOL_ROUTING_ENABLED",
    )
    call_web_search_enabled: bool = Field(
        default=False,
        validation_alias="CALL_WEB_SEARCH_ENABLED",
    )
    call_schedule_tools_enabled: bool = Field(
        default=False,
        validation_alias="CALL_SCHEDULE_TOOLS_ENABLED",
    )
    call_progress_speech_enabled: bool = Field(
        default=True,
        validation_alias="CALL_PROGRESS_SPEECH_ENABLED",
    )
    proactive_planner_temperature: float = Field(
        default=0.1,
        validation_alias="PROACTIVE_PLANNER_TEMPERATURE",
        ge=0.0,
        le=2.0,
    )
    proactive_planner_max_tokens: int = Field(
        default=320,
        validation_alias="PROACTIVE_PLANNER_MAX_TOKENS",
        ge=64,
        le=2048,
    )
    proactive_planner_format_retries: int = Field(
        default=1,
        validation_alias="PROACTIVE_PLANNER_FORMAT_RETRIES",
        ge=0,
        le=2,
    )
    timeout: int = Field(default=30, validation_alias="TIMEOUT")
    prompt_version: str = Field(default="echo-v1.1.0", validation_alias="PROMPT_VERSION")
    assistant_persona_version: str = Field(
        default="echo-persona-v3",
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
    desktop_pairing_code_ttl_seconds: int = Field(
        default=600,
        validation_alias="DESKTOP_PAIRING_CODE_TTL_SECONDS",
        ge=60,
        le=3600,
    )
    desktop_command_timeout_seconds: int = Field(
        default=45,
        validation_alias="DESKTOP_COMMAND_TIMEOUT_SECONDS",
        ge=10,
        le=120,
    )
    desktop_vision_enabled: bool = Field(
        default=True,
        validation_alias="DESKTOP_VISION_ENABLED",
    )
    desktop_vision_model: str = Field(
        default="deepseek-v4-flash-vision-exp",
        validation_alias="DESKTOP_VISION_MODEL",
    )
    desktop_vision_max_tokens: int = Field(
        default=500,
        validation_alias="DESKTOP_VISION_MAX_TOKENS",
        ge=100,
        le=2000,
    )
    desktop_capture_max_bytes: int = Field(
        default=3_000_000,
        validation_alias="DESKTOP_CAPTURE_MAX_BYTES",
        ge=100_000,
        le=10_000_000,
    )
    presence_enabled: bool = Field(
        default=True,
        validation_alias="PRESENCE_ENABLED",
    )
    presence_tick_interval_seconds: int = Field(
        default=900,
        validation_alias="PRESENCE_TICK_INTERVAL_SECONDS",
        ge=60,
        le=3600,
    )
    presence_active_window_minutes: int = Field(
        default=5,
        validation_alias="PRESENCE_ACTIVE_WINDOW_MINUTES",
        ge=1,
        le=60,
    )
    presence_silence_minutes: int = Field(
        default=30,
        validation_alias="PRESENCE_SILENCE_MINUTES",
        ge=5,
        le=720,
    )
    presence_min_thought_interval_minutes: int = Field(
        default=45,
        validation_alias="PRESENCE_MIN_THOUGHT_INTERVAL_MINUTES",
        ge=5,
        le=720,
    )
    presence_daily_thought_budget: int = Field(
        default=8,
        validation_alias="PRESENCE_DAILY_THOUGHT_BUDGET",
        ge=1,
        le=48,
    )
    presence_context_messages: int = Field(
        default=8,
        validation_alias="PRESENCE_CONTEXT_MESSAGES",
        ge=2,
        le=30,
    )
    presence_max_candidate_users: int = Field(
        default=20,
        validation_alias="PRESENCE_MAX_CANDIDATE_USERS",
        ge=1,
        le=200,
    )
    presence_thought_max_tokens: int = Field(
        default=300,
        validation_alias="PRESENCE_THOUGHT_MAX_TOKENS",
        ge=100,
        le=1200,
    )
    presence_thought_temperature: float = Field(
        default=0.9,
        validation_alias="PRESENCE_THOUGHT_TEMPERATURE",
        ge=0.0,
        le=2.0,
    )
    presence_proactive_message_budget: int = Field(
        default=3,
        validation_alias="PRESENCE_PROACTIVE_MESSAGE_BUDGET",
        ge=0,
        le=12,
    )
    presence_proactive_message_interval_minutes: int = Field(
        default=120,
        validation_alias="PRESENCE_PROACTIVE_MESSAGE_INTERVAL_MINUTES",
        ge=30,
        le=720,
    )
    presence_proactive_action_budget: int = Field(
        default=1,
        validation_alias="PRESENCE_PROACTIVE_ACTION_BUDGET",
        ge=0,
        le=6,
    )
    presence_proactive_action_interval_minutes: int = Field(
        default=240,
        validation_alias="PRESENCE_PROACTIVE_ACTION_INTERVAL_MINUTES",
        ge=30,
        le=1440,
    )
    presence_message_max_tokens: int = Field(
        default=180,
        validation_alias="PRESENCE_MESSAGE_MAX_TOKENS",
        ge=80,
        le=600,
    )
    presence_message_temperature: float = Field(
        default=0.8,
        validation_alias="PRESENCE_MESSAGE_TEMPERATURE",
        ge=0.0,
        le=2.0,
    )
    presence_memory_salience_threshold: float = Field(
        default=0.7,
        validation_alias="PRESENCE_MEMORY_SALIENCE_THRESHOLD",
        ge=0.0,
        le=1.0,
    )
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
    tts_speed: float = Field(default=1.05, validation_alias="TTS_SPEED", ge=0.5, le=2.0)
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
        default="用温柔、自然、亲近的语气连贯说话，语速稍快，句间只做极短停顿，不要长时间停顿，像在陪伴用户聊天。",
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
    cosyvoice_max_concurrent_streams: int = Field(
        default=2,
        validation_alias="COSYVOICE_MAX_CONCURRENT_STREAMS",
        ge=1,
        le=8,
    )
    voice_streaming_asr_enabled: bool = Field(
        default=False,
        validation_alias="VOICE_STREAMING_ASR_ENABLED",
    )
    echo_device_token: str = Field(default="", validation_alias="ECHO_DEVICE_TOKEN")
    echo_device_user_map_json: str = Field(
        default="{}",
        validation_alias="ECHO_DEVICE_USER_MAP_JSON",
    )
    echo_device_max_utterance_seconds: int = Field(
        default=30,
        validation_alias="ECHO_DEVICE_MAX_UTTERANCE_SECONDS",
        ge=1,
        le=120,
    )
    echo_device_max_opus_packet_bytes: int = Field(
        default=4096,
        validation_alias="ECHO_DEVICE_MAX_OPUS_PACKET_BYTES",
        ge=128,
        le=65535,
    )
    echo_device_auto_silence_ms: int = Field(
        default=500,
        validation_alias="ECHO_DEVICE_AUTO_SILENCE_MS",
        ge=300,
        le=3000,
    )
    echo_device_auto_minimum_speech_ms: int = Field(
        default=360,
        validation_alias="ECHO_DEVICE_AUTO_MINIMUM_SPEECH_MS",
        ge=60,
        le=2000,
    )
    echo_device_auto_speech_rms_threshold: int = Field(
        default=700,
        validation_alias="ECHO_DEVICE_AUTO_SPEECH_RMS_THRESHOLD",
        ge=1,
        le=32767,
    )
    echo_device_auto_no_speech_timeout_ms: int = Field(
        default=8000,
        validation_alias="ECHO_DEVICE_AUTO_NO_SPEECH_TIMEOUT_MS",
        ge=1000,
        le=60000,
    )
    echo_device_auto_maximum_speech_ms: int = Field(
        default=15000,
        validation_alias="ECHO_DEVICE_AUTO_MAXIMUM_SPEECH_MS",
        ge=1000,
        le=120000,
    )
    echo_device_playback_start_delay_ms: int = Field(
        default=120,
        validation_alias="ECHO_DEVICE_PLAYBACK_START_DELAY_MS",
        ge=0,
        le=1000,
    )
    echo_device_playback_prebuffer_packets: int = Field(
        default=10,
        validation_alias="ECHO_DEVICE_PLAYBACK_PREBUFFER_PACKETS",
        ge=0,
        le=20,
    )
    echo_device_playback_stop_grace_ms: int = Field(
        default=240,
        validation_alias="ECHO_DEVICE_PLAYBACK_STOP_GRACE_MS",
        ge=0,
        le=2000,
    )
    echo_device_streaming_enabled: bool = Field(
        default=False,
        validation_alias="ECHO_DEVICE_STREAMING_ENABLED",
    )
    echo_device_realtime_asr_enabled: bool = Field(
        default=False,
        validation_alias="ECHO_DEVICE_REALTIME_ASR_ENABLED",
    )
    echo_device_tts_chunk_max_chars: int = Field(
        default=18,
        validation_alias="ECHO_DEVICE_TTS_CHUNK_MAX_CHARS",
        ge=8,
        le=120,
    )
    echo_device_tts_chunk_min_chars: int = Field(
        default=8,
        validation_alias="ECHO_DEVICE_TTS_CHUNK_MIN_CHARS",
        ge=1,
        le=120,
    )
    echo_device_tts_prefetch_phrases: int = Field(
        default=2,
        validation_alias="ECHO_DEVICE_TTS_PREFETCH_PHRASES",
        ge=0,
        le=4,
    )
    echo_device_tts_max_silence_ms: int = Field(
        default=240,
        validation_alias="ECHO_DEVICE_TTS_MAX_SILENCE_MS",
        ge=60,
        le=1000,
    )
    echo_device_tts_silence_rms_threshold: int = Field(
        default=300,
        validation_alias="ECHO_DEVICE_TTS_SILENCE_RMS_THRESHOLD",
        ge=0,
        le=5000,
    )
    echo_device_streaming_prebuffer_packets: int = Field(
        default=4,
        validation_alias="ECHO_DEVICE_STREAMING_PREBUFFER_PACKETS",
        ge=1,
        le=12,
    )
    echo_device_audio_queue_max_packets: int = Field(
        default=40,
        validation_alias="ECHO_DEVICE_AUDIO_QUEUE_MAX_PACKETS",
        ge=4,
        le=200,
    )
    echo_firmware_version: str = Field(
        default="0.1.0",
        validation_alias="ECHO_FIRMWARE_VERSION",
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
    cos_enabled: bool = Field(default=False, validation_alias="COS_ENABLED")
    cos_bucket: str = Field(default="", validation_alias="COS_BUCKET")
    cos_region: str = Field(default="", validation_alias="COS_REGION")
    cos_secret_id: str = Field(default="", validation_alias="COS_SECRET_ID")
    cos_secret_key: str = Field(default="", validation_alias="COS_SECRET_KEY")
    cos_reuse_tencent_credentials: bool = Field(
        default=False,
        validation_alias="COS_REUSE_TENCENT_CREDENTIALS",
    )
    cos_custom_domain: str = Field(default="", validation_alias="COS_CUSTOM_DOMAIN")
    cos_private_read: bool = Field(default=True, validation_alias="COS_PRIVATE_READ")
    cos_object_prefix: str = Field(default="echo", validation_alias="COS_OBJECT_PREFIX")
    cos_signed_url_expires_seconds: int = Field(
        default=900,
        validation_alias="COS_SIGNED_URL_EXPIRES_SECONDS",
        ge=60,
        le=86400,
    )
    cos_timeout_seconds: int = Field(
        default=30,
        validation_alias="COS_TIMEOUT_SECONDS",
        ge=1,
        le=120,
    )
    release_download_url_expires_seconds: int = Field(
        default=14400,
        validation_alias="RELEASE_DOWNLOAD_URL_EXPIRES_SECONDS",
        ge=7200,
        le=21600,
    )
    release_rate_limit_requests: int = Field(
        default=60,
        validation_alias="RELEASE_RATE_LIMIT_REQUESTS",
        ge=1,
    )
    release_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias="RELEASE_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
    )
    voice_generated_retention_seconds: int = Field(
        default=3600,
        validation_alias="VOICE_GENERATED_RETENTION_SECONDS",
        ge=0,
    )
    voice_upload_retention_seconds: int = Field(
        default=300,
        validation_alias="VOICE_UPLOAD_RETENTION_SECONDS",
        ge=0,
    )
    voice_cleanup_interval_seconds: int = Field(
        default=600,
        validation_alias="VOICE_CLEANUP_INTERVAL_SECONDS",
        ge=0,
    )
    voice_cleanup_batch_size: int = Field(
        default=500,
        validation_alias="VOICE_CLEANUP_BATCH_SIZE",
        ge=1,
    )
    auth_token_secret: str = Field(default="", validation_alias="AUTH_TOKEN_SECRET")
    auth_token_expires_seconds: int = Field(
        default=900,
        validation_alias="AUTH_ACCESS_TOKEN_EXPIRES_SECONDS",
        ge=60,
        le=86400,
    )
    auth_jwt_issuer: str = Field(default="echo-backend", validation_alias="AUTH_JWT_ISSUER")
    auth_jwt_audience: str = Field(default="echo-app", validation_alias="AUTH_JWT_AUDIENCE")
    auth_jwt_key_id: str = Field(default="echo-v1", validation_alias="AUTH_JWT_KEY_ID")
    auth_jwt_previous_keys_json: str = Field(
        default="{}",
        validation_alias="AUTH_JWT_PREVIOUS_KEYS_JSON",
    )
    auth_refresh_token_pepper: str = Field(
        default="",
        validation_alias="AUTH_REFRESH_TOKEN_PEPPER",
    )
    auth_refresh_token_expires_seconds: int = Field(
        default=2592000,
        validation_alias="AUTH_REFRESH_TOKEN_EXPIRES_SECONDS",
        ge=3600,
        le=31536000,
    )
    auth_internal_fixture_phones: str = Field(
        default="",
        validation_alias="AUTH_INTERNAL_FIXTURE_PHONES",
    )
    sms_provider: str = Field(default="log", validation_alias="SMS_PROVIDER")
    sms_code_pepper: str = Field(default="", validation_alias="SMS_CODE_PEPPER")
    sms_challenge_expires_seconds: int = Field(
        default=300,
        validation_alias="SMS_CHALLENGE_EXPIRES_SECONDS",
        ge=60,
        le=900,
    )
    sms_resend_after_seconds: int = Field(
        default=60,
        validation_alias="SMS_RESEND_AFTER_SECONDS",
        ge=1,
        le=600,
    )
    sms_maximum_attempts: int = Field(
        default=5,
        validation_alias="SMS_MAXIMUM_ATTEMPTS",
        ge=1,
        le=10,
    )
    sms_log_verification_code: bool = Field(
        default=False,
        validation_alias="SMS_LOG_VERIFICATION_CODE",
    )
    sms_fixed_verification_code: str = Field(
        default="",
        validation_alias="SMS_FIXED_VERIFICATION_CODE",
    )
    sms_stub_delivery_enabled: bool = Field(
        default=False,
        validation_alias="SMS_STUB_DELIVERY_ENABLED",
    )
    aliyun_sms_access_key_id: str = Field(
        default="",
        validation_alias="ALIYUN_SMS_ACCESS_KEY_ID",
    )
    aliyun_sms_access_key_secret: str = Field(
        default="",
        validation_alias="ALIYUN_SMS_ACCESS_KEY_SECRET",
    )
    aliyun_sms_sign_name: str = Field(default="", validation_alias="ALIYUN_SMS_SIGN_NAME")
    aliyun_sms_template_code: str = Field(
        default="",
        validation_alias="ALIYUN_SMS_TEMPLATE_CODE",
    )
    tencent_sms_secret_id: str = Field(default="", validation_alias="TENCENT_SMS_SECRET_ID")
    tencent_sms_secret_key: str = Field(
        default="",
        validation_alias="TENCENT_SMS_SECRET_KEY",
    )
    tencent_sms_sdk_app_id: str = Field(
        default="",
        validation_alias="TENCENT_SMS_SDK_APP_ID",
    )
    tencent_sms_sign_name: str = Field(default="", validation_alias="TENCENT_SMS_SIGN_NAME")
    tencent_sms_template_id: str = Field(
        default="",
        validation_alias="TENCENT_SMS_TEMPLATE_ID",
    )
    sms_rate_limit_phone_requests: int = Field(
        default=5,
        validation_alias="SMS_RATE_LIMIT_PHONE_REQUESTS",
        ge=1,
    )
    sms_rate_limit_device_requests: int = Field(
        default=10,
        validation_alias="SMS_RATE_LIMIT_DEVICE_REQUESTS",
        ge=1,
    )
    sms_rate_limit_ip_requests: int = Field(
        default=20,
        validation_alias="SMS_RATE_LIMIT_IP_REQUESTS",
        ge=1,
    )
    sms_rate_limit_window_seconds: int = Field(
        default=3600,
        validation_alias="SMS_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
    )
    sms_global_daily_request_limit: int = Field(
        default=10000,
        validation_alias="SMS_GLOBAL_DAILY_REQUEST_LIMIT",
        ge=1,
    )
    auth_verify_rate_limit_requests: int = Field(
        default=10,
        validation_alias="AUTH_VERIFY_RATE_LIMIT_REQUESTS",
        ge=1,
    )
    auth_verify_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias="AUTH_VERIFY_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
    )
    auth_refresh_rate_limit_requests: int = Field(
        default=30,
        validation_alias="AUTH_REFRESH_RATE_LIMIT_REQUESTS",
        ge=1,
    )
    auth_refresh_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias="AUTH_REFRESH_RATE_LIMIT_WINDOW_SECONDS",
        ge=1,
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
    chat_async_enabled: bool = Field(
        default=True,
        validation_alias="CHAT_ASYNC_ENABLED",
    )
    chat_batch_quiet_window_ms: int = Field(
        default=2500,
        validation_alias="CHAT_BATCH_QUIET_WINDOW_MS",
        ge=100,
        le=5000,
    )
    chat_batch_max_window_ms: int = Field(
        default=10000,
        validation_alias="CHAT_BATCH_MAX_WINDOW_MS",
        ge=500,
        le=10000,
    )
    chat_batch_max_messages: int = Field(
        default=8,
        validation_alias="CHAT_BATCH_MAX_MESSAGES",
        ge=1,
        le=50,
    )
    chat_batch_max_chars: int = Field(
        default=6000,
        validation_alias="CHAT_BATCH_MAX_CHARS",
        ge=1,
        le=50000,
    )
    chat_queue_max_messages: int = Field(
        default=20,
        validation_alias="CHAT_QUEUE_MAX_MESSAGES",
        ge=1,
        le=200,
    )
    chat_worker_poll_interval_ms: int = Field(
        default=200,
        validation_alias="CHAT_WORKER_POLL_INTERVAL_MS",
        ge=50,
        le=5000,
    )
    chat_turn_lease_seconds: int = Field(
        default=180,
        validation_alias="CHAT_TURN_LEASE_SECONDS",
        ge=30,
        le=900,
    )
    chat_sse_heartbeat_seconds: int = Field(
        default=15,
        validation_alias="CHAT_SSE_HEARTBEAT_SECONDS",
        ge=5,
        le=60,
    )
    proactive_chat_enabled: bool = Field(
        default=True,
        validation_alias="PROACTIVE_CHAT_ENABLED",
    )
    proactive_chat_worker_interval_seconds: int = Field(
        default=30,
        validation_alias="PROACTIVE_CHAT_WORKER_INTERVAL_SECONDS",
        ge=5,
        le=300,
    )
    proactive_chat_job_lease_seconds: int = Field(
        default=180,
        validation_alias="PROACTIVE_CHAT_JOB_LEASE_SECONDS",
        ge=30,
        le=900,
    )
    push_enabled: bool = Field(
        default=False,
        validation_alias="PUSH_ENABLED",
    )
    getui_app_id: str = Field(default="", validation_alias="GETUI_APP_ID")
    getui_app_key: str = Field(default="", validation_alias="GETUI_APP_KEY")
    getui_master_secret: str = Field(
        default="",
        validation_alias="GETUI_MASTER_SECRET",
    )
    getui_harmony_app_id: str = Field(
        default="",
        validation_alias="GETUI_HARMONY_APP_ID",
    )
    getui_harmony_app_key: str = Field(
        default="",
        validation_alias="GETUI_HARMONY_APP_KEY",
    )
    getui_harmony_master_secret: str = Field(
        default="",
        validation_alias="GETUI_HARMONY_MASTER_SECRET",
    )
    getui_api_base_url: str = Field(
        default="https://restapi.getui.com/v2",
        validation_alias="GETUI_API_BASE_URL",
    )
    push_worker_interval_seconds: int = Field(
        default=15,
        validation_alias="PUSH_WORKER_INTERVAL_SECONDS",
        ge=5,
        le=300,
    )
    chat_followup_text_delay_ms: int = Field(
        default=1200,
        validation_alias="CHAT_FOLLOWUP_TEXT_DELAY_MS",
        ge=0,
        le=5000,
    )
    chat_final_text_delay_ms: int = Field(
        default=2000,
        validation_alias="CHAT_FINAL_TEXT_DELAY_MS",
        ge=0,
        le=5000,
    )
    chat_sticker_delay_ms: int = Field(
        default=1000,
        validation_alias="CHAT_STICKER_DELAY_MS",
        ge=0,
        le=5000,
    )
    chat_max_total_delay_ms: int = Field(
        default=15000,
        validation_alias="CHAT_MAX_TOTAL_DELAY_MS",
        ge=3000,
        le=30000,
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
    daily_letter_worker_batch_size: int = Field(
        default=20,
        validation_alias="DAILY_LETTER_WORKER_BATCH_SIZE",
        ge=1,
        le=200,
    )
    daily_letter_generation_version: str = Field(
        default="letter-agent-v2", validation_alias="DAILY_LETTER_GENERATION_VERSION"
    )
    daily_letter_max_attempts: int = Field(
        default=3, validation_alias="DAILY_LETTER_MAX_ATTEMPTS", ge=1, le=5
    )
    daily_letter_retry_offsets_seconds: str = Field(
        default="300,720",
        validation_alias="DAILY_LETTER_RETRY_OFFSETS_SECONDS",
    )
    daily_letter_agent_timeout_seconds: int = Field(
        default=120,
        validation_alias="DAILY_LETTER_AGENT_TIMEOUT_SECONDS",
        ge=10,
        le=300,
    )
    daily_letter_agent_max_steps: int = Field(
        default=2,
        validation_alias="DAILY_LETTER_AGENT_MAX_STEPS",
        ge=1,
        le=4,
    )
    daily_letter_max_tokens: int = Field(
        default=2500,
        validation_alias="DAILY_LETTER_MAX_TOKENS",
        ge=500,
        le=8192,
    )
    daily_letter_target_min_chars: int = Field(
        default=600,
        validation_alias="DAILY_LETTER_TARGET_MIN_CHARS",
        ge=100,
        le=2000,
    )
    daily_letter_target_max_chars: int = Field(
        default=1000,
        validation_alias="DAILY_LETTER_TARGET_MAX_CHARS",
        ge=200,
        le=4000,
    )
    daily_letter_context_version: str = Field(
        default="daily-letter-context-v2",
        validation_alias="DAILY_LETTER_CONTEXT_VERSION",
    )
    letter_image_generation_enabled: bool = Field(
        default=False,
        validation_alias="LETTER_IMAGE_GENERATION_ENABLED",
    )
    minimax_image_api_key: str = Field(
        default="", validation_alias="MINIMAX_IMAGE_API_KEY"
    )
    minimax_image_base_url: str = Field(
        default="https://api.minimaxi.com/v1/image_generation",
        validation_alias="MINIMAX_IMAGE_BASE_URL",
    )
    minimax_image_model: str = Field(
        default="image-01",
        validation_alias="MINIMAX_IMAGE_MODEL",
    )
    minimax_image_timeout_seconds: int = Field(
        default=120, validation_alias="MINIMAX_IMAGE_TIMEOUT_SECONDS", ge=10, le=300
    )
    letter_image_aspect_ratio: str = Field(
        default="4:3", validation_alias="LETTER_IMAGE_ASPECT_RATIO"
    )
    letter_image_max_attempts: int = Field(
        default=2, validation_alias="LETTER_IMAGE_MAX_ATTEMPTS", ge=1, le=3
    )
    letter_image_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias="LETTER_IMAGE_MAX_BYTES",
        ge=1024,
        le=20 * 1024 * 1024,
    )
    letter_image_reference_asset: str = Field(
        default="", validation_alias="LETTER_IMAGE_REFERENCE_ASSET"
    )
    sticker_enabled: bool = Field(default=True, validation_alias="STICKER_ENABLED")
    sticker_upload_max_bytes: int = Field(
        default=5 * 1024 * 1024,
        validation_alias="STICKER_UPLOAD_MAX_BYTES",
        ge=1024,
        le=20 * 1024 * 1024,
    )
    sticker_vector_search_enabled: bool = Field(
        default=True,
        validation_alias="STICKER_VECTOR_SEARCH_ENABLED",
    )
    sticker_vector_top_k: int = Field(
        default=12,
        validation_alias="STICKER_VECTOR_TOP_K",
        ge=3,
        le=100,
    )
    sticker_vector_score_threshold: float = Field(
        default=0.55,
        validation_alias="STICKER_VECTOR_SCORE_THRESHOLD",
        ge=-1.0,
        le=1.0,
    )
    sticker_vector_max_score_gap: float = Field(
        default=0.04,
        validation_alias="STICKER_VECTOR_MAX_SCORE_GAP",
        ge=0.0,
        le=1.0,
    )
    sticker_embedding_backfill_limit: int = Field(
        default=500,
        validation_alias="STICKER_EMBEDDING_BACKFILL_LIMIT",
        ge=1,
        le=10000,
    )
    conversation_active_max_seconds: int = Field(
        default=120,
        validation_alias="CONVERSATION_ACTIVE_MAX_SECONDS",
        ge=1,
    )
    conversation_returned_min_seconds: int = Field(
        default=1800,
        validation_alias="CONVERSATION_RETURNED_MIN_SECONDS",
        ge=60,
    )
    conversation_long_absence_seconds: int = Field(
        default=21600,
        validation_alias="CONVERSATION_LONG_ABSENCE_SECONDS",
        ge=300,
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
        "Echo 是以情感陪伴为核心的 AI 伙伴。通过真实交流建立长期关系，"
        "按用户明确选择以朋友或 AI 恋人的方式平等相处；具体人格由独立人格材料定义。"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
