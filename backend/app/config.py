"""Read database settings from the environment, never from committed secrets."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Local host development uses the mapped PostgreSQL port; Compose will override it.
    database_url: str = "postgresql+psycopg://tasks_app:tasks_dev_only@localhost:5432/tasks"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
