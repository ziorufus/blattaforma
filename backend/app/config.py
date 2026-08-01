from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    admin_email: str = "admin@example.com"

    google_client_id: str = ""
    google_client_secret: str = ""

    secret_key: str = "change-me-to-a-random-secret"
    access_token_expire_minutes: int = 30

    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    db_path: str = ""

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", case_sensitive=False)

    @property
    def database_url(self) -> str:
        path = self.db_path or str(BASE_DIR / "blattaforma.db")
        return f"sqlite:///{path}"


settings = Settings()
