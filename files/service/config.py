from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "analytics"
    clickhouse_user: str = "admin"
    clickhouse_password: str = "admin"

    zenlabs_base_url: str = "https://zenarate-web-prod.fly.dev"
    zenlabs_token: str = "ccbd85c437e16daadf85c51b0490c1d5448067576b7ef6f28ec19319189b514d 18"
    tenant_id: str = "wks_taj_group"
    default_property_id: str = "thv_goa"

    poll_interval_seconds: int = 300


settings = Settings()
