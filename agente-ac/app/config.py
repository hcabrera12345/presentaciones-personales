"""Configuración por variables de entorno (ver .env.example)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    entorno: str = "desarrollo"                 # desarrollo | produccion
    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    supabase_url: str = ""
    supabase_anon_key: str = ""                 # pública: la usa el navegador para el login con Google
    supabase_service_key: str = ""              # secreta: solo servidor (Storage)
    supabase_jwt_secret: str = ""               # solo si el proyecto usa la firma HS256 heredada

    claude_modelo: str = "claude-opus-5-5"      # ANTHROPIC_API_KEY la lee el SDK directamente
    groq_api_key: str = ""
    proxy_youtube: str = ""                     # http://usuario:clave@host:puerto del proxy residencial
    canal_youtube_id: str = ""                  # UC… del canal de Asuntos Centrales (detección automática)

    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_verify_token: str = ""
    facebook_page_id: str = ""
    facebook_token: str = ""                    # token del usuario del sistema de Meta
    graph_api_version: str = "v23.0"

    carpeta_trabajo: str = "/tmp/agente"
    auth_desactivada: bool = False              # SOLO desarrollo local; se ignora en producción

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"


@lru_cache
def config() -> Config:
    return Config()
