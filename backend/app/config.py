from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    keitaro_base_url: str = "https://tlgk.host"
    keitaro_api_key: str = ""
    database_url: str = "sqlite:///./keitaro_wrapper.db"
    frontend_origin: str = "http://localhost:5173"
    campaign_prefix: str = "test_antipov_"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
