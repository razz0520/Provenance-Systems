import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    # Database & Redis
    DATABASE_URL: str = "postgresql://provenance:provenance123@localhost:5432/provenance_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security & JWT
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # WhatsApp Integration
    WHATSAPP_APP_ID: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "provenance-verify-token-2024"

    # File Storage & Limits
    MAX_UPLOAD_SIZE: int = 16777216  # 16 MB
    MEDIA_PROCESSING_TIMEOUT_SECONDS: int = 120  # Generous safety ceiling (2 mins) for media processing
    ALLOWED_EXTENSIONS: str = "mp4,avi,mov,mp3,wav,jpg,png,pdf,txt"
    UPLOAD_DIR: str = "uploads"
    TEMP_DIR: str = "uploads/temp"
    PROCESSED_DIR: str = "uploads/processed"

    # API Configuration
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Tunneling
    NGROK_AUTHTOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=[
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
            ".env",
        ],
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)


settings = Settings()
