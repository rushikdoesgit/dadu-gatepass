import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Advanced Gatepass System"
    ENV: str = "development"
    DEBUG: bool = True
    
    # Database Settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite+aiosqlite:///gatepass.db"
    )
    
    # Cryptography & OTP parameters
    QR_STEP_INTERVAL_SECONDS: int = 45
    AES_ENCRYPTION_KEY: str = os.getenv(
        "AES_ENCRYPTION_KEY", 
        "32_byte_secret_key_for_aes_encryption_here_!!!!"
    )
    
    # SWD Integration Settings
    SWD_ISSUER: str = "https://swd.campus.edu"
    SWD_CLIENT_ID: str = "gatepass_system_client"
    SWD_JWKS_URL: str = os.getenv(
        "SWD_JWKS_URL", 
        "http://localhost:8000/api/v1/mock-swd/.well-known/jwks.json"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
