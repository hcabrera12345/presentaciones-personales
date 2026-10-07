"""Archivos en Supabase Storage (bucket privado). Se accede con la clave de servicio, solo desde el servidor."""
from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx


class Almacenamiento:
    def __init__(self, supabase_url: str, service_key: str, bucket: str = "medios"):
        self.base = f"{supabase_url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def subir(self, local: Path, ruta: str) -> str:
        tipo = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        with local.open("rb") as f:
            r = httpx.post(f"{self.base}/object/{self.bucket}/{ruta}", content=f,
                           headers={**self.headers, "Content-Type": tipo, "x-upsert": "true"}, timeout=600)
        r.raise_for_status()
        return ruta

    def descargar(self, ruta: str, local: Path) -> Path:
        with httpx.stream("GET", f"{self.base}/object/{self.bucket}/{ruta}", headers=self.headers,
                          timeout=600) as r:
            r.raise_for_status()
            with local.open("wb") as f:
                for parte in r.iter_bytes():
                    f.write(parte)
        return local

    def url_firmada(self, ruta: str, segundos: int = 3600) -> str:
        r = httpx.post(f"{self.base}/object/sign/{self.bucket}/{ruta}", json={"expiresIn": segundos},
                       headers=self.headers, timeout=30)
        r.raise_for_status()
        return f"{self.base}{r.json()['signedURL']}"
