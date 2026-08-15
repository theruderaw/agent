from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    app_name: str = "agent"
    app_env: str = "development"
    debug: bool = True

    # Database
    database_url: str

    # Ollama
    ollama_url: str = "http://localhost:11434"

    ollama_base_model: str = "qwen2.5-coder:3b"
    ollama_think_model: str = "qwen2.5-coder:7b"

    ollama_connect_timeout: float = 5
    ollama_read_timeout: float = 120
    ollama_write_timeout: float = 40

    # Runtime
    max_iterations: int = 50

    # Worker
    worker_concurrency: int = 1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()