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

    ollama_max_minutes: int = 25

    # Ogni quanti minuti il worker "leader" rinfresca il keep_alive dei
    # modelli bloccati in RAM (e ricarica quelli eventualmente caduti).
    ollama_pin_refresh_minutes: int = 5

    # Percorso del file lock che elegge l'unico worker che esegue il refresh
    # dei modelli bloccati. Vuoto = backend/ollama_pin_scheduler.lock.
    ollama_pin_scheduler_lock_path: str = ""

    # keep_alive applicato quando un modello viene sbloccato: riporta il runner
    # da "infinito" a una scadenza normale. Formato Ollama (es. "30m", "1h").
    ollama_default_keep_alive: str = "30m"

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", case_sensitive=False)

    @property
    def database_url(self) -> str:
        path = self.db_path or str(BASE_DIR / "blattaforma.db")
        return f"sqlite:///{path}"


settings = Settings()
