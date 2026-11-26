"""Load application configuration from environment variables.

Database credentials must be provided at runtime.
No database passwords or connection strings containing
credentials should be hardcoded in this module.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Require DATABASE_URL to be supplied through the environment.
    #
    # If the variable is missing, Pydantic raises a validation
    # error instead of falling back to hardcoded credentials.
    #
    # Docker Compose supplies the PostgreSQL connection string.
    # Automated tests supply an isolated SQLite connection string.
    database_url: str

    # Support local environment files while ignoring unrelated
    # configuration variables.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


# Initialize and validate configuration when the module is imported.
settings = Settings()
