from typing import Literal

from pydantic import BaseModel, Field, SecretStr, VERSION

PYDANTIC_V2 = int(VERSION.split(".")[0]) >= 2


def secret_field(default=..., **limits):
    if PYDANTIC_V2:
        return Field(default, **limits)
    return Field(default, **{f"secret_{key}": value for key, value in limits.items()})


def options_field():
    return Field(default_factory=list, **({"max_length": 50} if PYDANTIC_V2 else {"max_items": 50}))


class Input(BaseModel):
    if PYDANTIC_V2:
        model_config = {"extra": "forbid"}
    else:
        from pydantic import validator

        class Config:
            extra = "forbid"

        @validator("*", allow_reuse=True)
        def secret_limits(cls, value, field):
            if isinstance(value, SecretStr):
                size = len(value.get_secret_value())
                limits = field.field_info.extra
                if size < limits.get("secret_min_length", 0) or size > limits.get("secret_max_length", float("inf")):
                    raise ValueError("敏感字段长度不符合要求")
            return value

        def model_dump(self, **kwargs):
            return self.dict(**kwargs)


class Login(Input):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = secret_field(min_length=1, max_length=256)


class Setup(Login):
    password: SecretStr = secret_field(min_length=12, max_length=256)
    setup_token: SecretStr = secret_field(min_length=24, max_length=256)


class AccountCreate(Input):
    label: str = Field(min_length=1, max_length=80)
    username: SecretStr = secret_field(min_length=1, max_length=128)
    password: SecretStr = secret_field(min_length=1, max_length=256)


class AccountUpdate(Input):
    label: str = Field(min_length=1, max_length=80)
    password: SecretStr | None = secret_field(default=None, min_length=1, max_length=256)


class TaskAction(Input):
    action: Literal["pause", "resume", "stop", "retry"]


class LearningSelection(Input):
    course_ids: list[int] = Field(default_factory=list)
    revision: int = Field(ge=0)
    fingerprint: str | None = Field(default=None, min_length=64, max_length=64)


class LearningAction(Input):
    action: Literal["start", "pause", "resume", "stop", "refresh"]
    revision: int | None = Field(default=None, ge=0)
    fingerprint: str | None = Field(default=None, min_length=64, max_length=64)


class SettingsUpdate(Input):
    concurrency: int = Field(ge=1, le=8)
    retry_seconds: int = Field(ge=5, le=3600)
    max_attempts: int = Field(ge=1, le=5)
    log_retention_days: int = Field(ge=1, le=365)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    completion_tone: bool = False
    color_log: bool = True
    log_out_file: bool = False


class AISettings(Input):
    enabled: bool = False
    base_url: str = Field(default="https://api.openai.com/v1", max_length=256)
    model: str = Field(default="", max_length=128)
    api_key: SecretStr | None = secret_field(default=None, max_length=512)
    api_style: Literal["chat", "responses", "metaso"] = "chat"


class StudySettings(Input):
    answer_mode: Literal["off", "ai", "question_bank", "chaoxing_ai"] = "off"
    submit_mode: Literal["save", "submit", "complete"] = "save"
    video_mode: Literal["off", "normal", "multi_course", "multi_node"] = "normal"
    node_concurrency: int = Field(default=2, ge=1, le=7)
    media_client: Literal["desktop", "mobile"] = "desktop"
    audio: bool = True
    document: bool = True
    read: bool = True
    hyperlink: bool = True
    chapter_test: bool = True
    work: bool = False
    exam: bool = False
    shuffle: bool = False
    include_courses: list[str] = Field(default_factory=list)
    exclude_courses: list[str] = Field(default_factory=list)
    execution_timeout: int = Field(default=28800, ge=30, le=86400)


class QuestionBankSettings(Input):
    enabled: bool = False
    url: str = Field(default="", max_length=512)
    token: SecretStr | None = secret_field(default=None, max_length=512)
    ai_fallback: bool = False
    allow_lan: bool = False


class AccountPreferences(Input):
    inform_emails: list[str] = Field(default_factory=list)
    proxy_url: SecretStr | None = secret_field(default=None, max_length=512)


class ConfigImport(Input):
    text: SecretStr = secret_field(min_length=1, max_length=100000)


class PlanStart(Input):
    fingerprint: str = Field(min_length=64, max_length=64)


class EmailSettings(Input):
    enabled: bool = False
    host: str = Field(default="", max_length=253)
    port: int = Field(default=465, ge=1, le=65535)
    security: Literal["ssl", "starttls"] = "ssl"
    username: str = Field(default="", max_length=254)
    password: SecretStr | None = secret_field(default=None, max_length=512)
    sender: str = Field(default="", max_length=254)
    recipients: list[str] = Field(default_factory=list)
    on_success: bool = True
    on_failure: bool = True
    on_attention: bool = True


class AIPreview(Input):
    question: str = Field(min_length=1, max_length=16000)
    options: list[str] = options_field()
    question_type: str = Field(default="unknown", max_length=40)
