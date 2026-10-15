from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    admin_email: str = "admin@example.com"

    google_client_id: str = ""
    google_client_secret: str = ""

    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"

    secret_key: str = "change-me-to-a-random-secret"
    access_token_expire_minutes: int = 30

    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    db_path: str = ""

    # Le altre impostazioni del modulo Ollama sono opzioni modificabili
    # dall'interfaccia di amministrazione (MODULE_OPTIONS in modules/ollama.py).

    # Percorso del file lock che elegge l'unico worker che esegue il refresh
    # dei modelli bloccati. Vuoto = backend/ollama_pin_scheduler.lock.
    ollama_pin_scheduler_lock_path: str = ""

    # extra="ignore": un .env che contiene ancora variabili ormai spostate tra
    # le opzioni (es. OLLAMA_MAX_MINUTES) non deve impedire l'avvio.
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", case_sensitive=False, extra="ignore")

    @property
    def database_url(self) -> str:
        path = self.db_path or str(BASE_DIR / "blattaforma.db")
        return f"sqlite:///{path}"


settings = Settings()
