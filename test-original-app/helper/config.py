"""Configuración leída del .env de la raíz del repo (variables con prefijo CAJA_)."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP = Path(__file__).resolve().parents[1]  # test-original-app/
RAIZ = APP.parent  # raíz del repo, donde está el .env


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        env_prefix="CAJA_",
        extra="ignore",
    )

    token: SecretStr
    url: str = "https://caja-negra-production-c64f.up.railway.app"
    log: Path = APP / "experimentos.jsonl"
    max_rps: float = 8  # el límite del reto es 10/s por token
    timeout: float = 15
