from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "KISnet-POS"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "sqlite:///./app.db"
    BUSINESS_TIMEZONE: str = "America/New_York"
    EXPORT_DIR: str = "exports"  # end-of-day CSV files, one folder per business day

settings = Settings()