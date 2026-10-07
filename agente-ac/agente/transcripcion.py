"""Transcripción con Whisper vía Groq (API compatible con OpenAI).

El audio se convierte a mono 16 kHz y se parte en bloques de 10 minutos para respetar el
límite de tamaño por archivo de la API; los tiempos de cada bloque se desplazan a su
posición real en la entrevista.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import httpx

from agente.diseno import duracion, ejecutar

URL_GROQ = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELO_GROQ = "whisper-large-v3-turbo"
BLOQUE_S = 600


def _transcribir_bloque(ruta: Path, api_key: str, idioma: str) -> dict:
    with ruta.open("rb") as f:
        r = httpx.post(
            URL_GROQ,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (ruta.name, f, "audio/mpeg")},
            data=[("model", MODELO_GROQ), ("language", idioma), ("response_format", "verbose_json"),
                  ("timestamp_granularities[]", "segment"), ("timestamp_granularities[]", "word")],
            timeout=300,
        )
    r.raise_for_status()
    return r.json()


def transcribir(audio_o_video: Path, api_key: str, idioma: str = "es") -> list[dict]:
    """Devuelve segmentos [{inicio, fin, texto, palabras:[{inicio, fin, p}]}] con tiempos absolutos."""
    total = duracion(audio_o_video)
    segmentos: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, desde in enumerate(range(0, int(total) + 1, BLOQUE_S)):
            bloque = Path(tmp) / f"bloque_{n}.mp3"
            ejecutar(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(desde), "-t", str(BLOQUE_S),
                      "-i", str(audio_o_video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(bloque)])
            if bloque.stat().st_size < 1000:
                continue
            datos = _transcribir_bloque(bloque, api_key, idioma)
            palabras = datos.get("words") or []
            for s in datos.get("segments") or []:
                ini, fin = s["start"], s["end"]
                segmentos.append({
                    "inicio": round(desde + ini, 2),
                    "fin": round(desde + fin, 2),
                    "texto": s["text"].strip(),
                    "palabras": [{"inicio": round(desde + w["start"], 2), "fin": round(desde + w["end"], 2),
                                  "p": w["word"].strip()}
                                 for w in palabras if ini <= w["start"] < fin],
                })
    return segmentos
