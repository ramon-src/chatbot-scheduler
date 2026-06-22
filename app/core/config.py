"""
Application configuration using Pydantic Settings
"""

import os
from typing import List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # =============================================================================
    # ENVIRONMENT
    # =============================================================================
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    TESTING: bool = Field(default=False, env="TESTING")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # =============================================================================
    # API CONFIGURATION
    # =============================================================================
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    API_PREFIX: str = Field(default="/api/v1", env="API_PREFIX")
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000"], env="CORS_ORIGINS")
    
    # =============================================================================
    # DATABASE
    # =============================================================================
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_URL_TEST: Optional[str] = Field(default=None, env="DATABASE_URL_TEST")
    
    # =============================================================================
    # REDIS
    # =============================================================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_SESSION_DB: int = Field(default=1, env="REDIS_SESSION_DB")
    REDIS_CACHE_DB: int = Field(default=2, env="REDIS_CACHE_DB")
    
    # =============================================================================
    # OPENAI
    # =============================================================================
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-4o", env="OPENAI_MODEL")
    OPENAI_TEMPERATURE: float = Field(default=0.7, env="OPENAI_TEMPERATURE")
    OPENAI_MAX_TOKENS: int = Field(default=4000, env="OPENAI_MAX_TOKENS")
    
    # =============================================================================
    # OPENROUTER (fallback provider for LLM)
    # =============================================================================
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, env="OPENROUTER_API_KEY")

    # =============================================================================
    # AGENT
    # =============================================================================
    SIMPLIFICA_AGENT_MODEL: str = Field(default="gpt-5.4-mini", env="SIMPLIFICA_AGENT_MODEL")
    TIMEZONE: str = Field(default="America/Sao_Paulo", env="TIMEZONE")

    # =============================================================================
    # GOOGLE CALENDAR
    # =============================================================================
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:8000/auth/google/callback", env="GOOGLE_REDIRECT_URI")
    GOOGLE_SCOPES: List[str] = Field(default=["https://www.googleapis.com/auth/calendar"], env="GOOGLE_SCOPES")
    GOOGLE_CLIENT_EMAIL: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_EMAIL")
    GOOGLE_PRIVATE_KEY: Optional[str] = Field(default=None, env="GOOGLE_PRIVATE_KEY")

    # =============================================================================
    # WHATSAPP BUSINESS API
    # =============================================================================
    WHATSAPP_ACCESS_TOKEN: Optional[str] = Field(default=None, env="WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = Field(default=None, env="WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: Optional[str] = Field(default=None, env="WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    WHATSAPP_API_URL: str = Field(default="https://graph.facebook.com/v18.0", env="WHATSAPP_API_URL")
    # Meta app secret for X-Hub-Signature-256 verification (optional; disables check if unset)
    WHATSAPP_APP_SECRET: Optional[str] = Field(default=None, env="WHATSAPP_APP_SECRET")

    # =============================================================================
    # EVOLUTION API (default WhatsApp provider)
    # =============================================================================
    EVOLUTION_API_URL: Optional[str] = Field(default=None, env="EVOLUTION_API_URL")
    EVOLUTION_API_KEY: Optional[str] = Field(default=None, env="EVOLUTION_API_KEY")
    EVOLUTION_INSTANCE: Optional[str] = Field(default=None, env="EVOLUTION_INSTANCE")
    EVOLUTION_WEBHOOK_TOKEN: Optional[str] = Field(default=None, env="EVOLUTION_WEBHOOK_TOKEN")
    
    # =============================================================================
    # SECURITY
    # =============================================================================
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # =============================================================================
    # LOGGING
    # =============================================================================
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")
    LOG_FILE: str = Field(default="logs/simplificapsi.log", env="LOG_FILE")
    LOG_MAX_SIZE: str = Field(default="10MB", env="LOG_MAX_SIZE")
    LOG_BACKUP_COUNT: int = Field(default=5, env="LOG_BACKUP_COUNT")
    
    # =============================================================================
    # MONITORING
    # =============================================================================
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    HEALTH_CHECK_INTERVAL: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    
    # =============================================================================
    # DEVELOPMENT
    # =============================================================================
    RELOAD: bool = Field(default=True, env="RELOAD")
    WORKERS: int = Field(default=1, env="WORKERS")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    
    # =============================================================================
    # VALIDATORS
    # =============================================================================
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("GOOGLE_SCOPES", pre=True)
    def parse_google_scopes(cls, v):
        if isinstance(v, str):
            return [scope.strip() for scope in v.split(",")]
        return v
    
    @validator("DATABASE_URL", pre=True)
    def validate_database_url(cls, v):
        if not v:
            raise ValueError("DATABASE_URL is required")
        return v
    
    @validator("OPENAI_API_KEY", pre=True)
    def validate_openai_key(cls, v):
        if not v or v == "your_openai_api_key_here":
            raise ValueError("OPENAI_API_KEY is required")
        return v
    
    @validator("SECRET_KEY", pre=True)
    def validate_secret_key(cls, v):
        if not v or v == "your_secret_key_here_change_in_production":
            raise ValueError("SECRET_KEY must be set to a secure value")
        return v
    
    @validator("JWT_SECRET_KEY", pre=True)
    def validate_jwt_secret_key(cls, v):
        if not v or v == "your_jwt_secret_key_here_change_in_production":
            raise ValueError("JWT_SECRET_KEY must be set to a secure value")
        return v
    
    # =============================================================================
    # PROPERTIES
    # =============================================================================
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    @property
    def is_testing(self) -> bool:
        return self.TESTING
    
    @property
    def database_url(self) -> str:
        """Get database URL based on environment"""
        if self.TESTING and self.DATABASE_URL_TEST:
            return self.DATABASE_URL_TEST
        return self.DATABASE_URL
    
    @property
    def redis_session_url(self) -> str:
        """Get Redis session URL"""
        return self.REDIS_URL.replace("/0", f"/{self.REDIS_SESSION_DB}")
    
    @property
    def redis_cache_url(self) -> str:
        """Get Redis cache URL"""
        return self.REDIS_URL.replace("/0", f"/{self.REDIS_CACHE_DB}")
    
    # =============================================================================
    # CONFIGURATION
    # =============================================================================
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # tolerate unknown keys in .env (don't crash on stray vars)

# =============================================================================
# GLOBAL SETTINGS INSTANCE
# =============================================================================
settings = Settings()

# Bridge credentials from settings (.env) into the process environment so
# third-party SDKs (OpenAI / OpenRouter) that read os.environ directly can
# find them. pydantic-settings only populates the `settings` object, not the
# OS env, so without this the LLM clients fail with "Missing credentials".
for _cred_key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
    _cred_val = getattr(settings, _cred_key, None)
    if _cred_val:
        os.environ.setdefault(_cred_key, _cred_val)

