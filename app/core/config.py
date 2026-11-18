from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "KISnet-POS"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "sqlite:///./app.db"
    BUSINESS_TIMEZONE: str = "America/New_York"
    RECEIPT_TEMPLATE: str = "app/templates/receipt.txt"  # guest receipt layout; edit the file, no restart needed
    LOOKIN_HOURS: int = 12  # how long a look-in portal sign-in lasts
    LOOKIN_REQUIRE_TWO_STEP: bool = True  # the look-in portal can face the internet: PIN alone is not enough
    EXPORT_DIR: str = "exports"  # end-of-day CSV files, one folder per business day

settings = Settings()