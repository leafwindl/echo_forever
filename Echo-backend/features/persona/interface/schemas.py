from pydantic import BaseModel, Field


class PersonaUpdateRequest(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=40)
    reply_style: str = Field(default="natural", max_length=32)
    reply_length: str = Field(default="balanced", max_length=32)
    support_mode: str = Field(default="balanced", max_length=32)
    proactivity: str = Field(default="balanced", max_length=32)
    avoid_topics: list[str] = Field(default_factory=list, max_length=5)
    about_user: str | None = Field(default=None, max_length=300)
    enabled: bool = True


class PersonaResponse(BaseModel):
    preferred_name: str | None = None
    reply_style: str
    reply_length: str
    support_mode: str
    proactivity: str
    avoid_topics: list[str]
    about_user: str | None = None
    enabled: bool
    schema_version: int
    is_customized: bool
    created_at: str | None = None
    updated_at: str | None = None
