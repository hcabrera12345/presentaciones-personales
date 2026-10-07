"""Acceso a los medios de origen: archivo propio o video de YouTube.

De YouTube solo se descarga lo necesario (el audio para transcribir y tramos cortos para
capturas y clips), a través de un proxy residencial: los servidores en la nube están
bloqueados por YouTube y el proxy se cobra por GB.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agente.diseno import ejecutar


def _yt_dlp(args: list[str], proxy: str | None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-progress"]
    if proxy:
        cmd += ["--proxy", proxy]
    r = subprocess.run(cmd + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp falló: {r.stderr[-1500:]}")
    return r


def info_youtube(url: str, proxy: str | None) -> dict:
    datos = json.loads(_yt_dlp(["-J", url], proxy).stdout)
    return {"youtube_id": datos["id"], "titulo": datos.get("title", ""), "duracion_s": datos.get("duration"),
            "canal": datos.get("channel", ""), "publicado": datos.get("upload_date"),
            "en_vivo": datos.get("live_status") in ("is_live", "is_upcoming", "post_live")}


class Fuente:
    """Un video de origen. `audio()` y `tramo()` devuelven archivos locales listos para ffmpeg."""

    def __init__(self, carpeta: Path, *, archivo: Path | None = None, url: str | None = None,
                 proxy: str | None = None):
        if not archivo and not url:
            raise ValueError("Se necesita un archivo o una URL")
        self.carpeta, self.archivo, self.url, self.proxy = carpeta, archivo, url, proxy
        carpeta.mkdir(parents=True, exist_ok=True)

    def audio(self) -> Path:
        if self.archivo:
            return self.archivo
        destino = self.carpeta / "audio.m4a"
        if not destino.exists():
            _yt_dlp(["-f", "bestaudio[ext=m4a]/bestaudio", "-o", str(destino), self.url], self.proxy)
        return destino

    def tramo(self, ini: float, fin: float, nombre: str) -> Path:
        destino = self.carpeta / f"{nombre}.mp4"
        if destino.exists():
            return destino
        ini = max(ini, 0)
        if self.archivo:
            ejecutar(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ini:.2f}", "-t", f"{fin - ini:.2f}",
                      "-i", str(self.archivo), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                      "-c:a", "aac", str(destino)])
        else:
            _yt_dlp(["-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                     "--download-sections", f"*{ini:.2f}-{fin:.2f}", "--force-keyframes-at-cuts",
                     "-o", str(destino), self.url], self.proxy)
        return destino
