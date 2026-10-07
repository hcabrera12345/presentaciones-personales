"""Verificación de citas: ninguna propuesta sale si su cita no está en la transcripción.

Además corrige el segundo de cada cita con el tiempo real de la transcripción, para que
las capturas y los clips caigan en el momento exacto.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

UMBRAL_SIMILITUD = 0.88  # tolera diferencias mínimas de puntuación o una palabra mal transcrita


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", texto)).strip()


def _palabras_con_tiempo(segmentos: list[dict]) -> list[tuple[str, float]]:
    salida = []
    for s in segmentos:
        palabras = s.get("palabras") or []
        if palabras:
            salida += [(normalizar(w["p"]), w["inicio"]) for w in palabras if normalizar(w["p"])]
        else:  # sin marcas por palabra: todas las palabras de la frase toman el inicio de la frase
            salida += [(p, s["inicio"]) for p in normalizar(s["texto"]).split()]
    return salida


def ubicar_cita(cita: str, segmentos: list[dict]) -> tuple[float, float] | None:
    """Devuelve (similitud, segundo_de_inicio) del mejor tramo que coincide con la cita, o None."""
    objetivo = normalizar(cita).split()
    palabras = _palabras_con_tiempo(segmentos)
    if not objetivo or len(palabras) < len(objetivo):
        return None
    n = len(objetivo)
    texto_obj = " ".join(objetivo)
    mejor = (0.0, 0.0)
    for i in range(len(palabras) - n + 1):
        if palabras[i][0] != objetivo[0] and palabras[i + n - 1][0] != objetivo[-1]:
            continue  # descarte rápido: ni la primera ni la última palabra coinciden
        ventana = " ".join(p for p, _ in palabras[i:i + n])
        ratio = 1.0 if ventana == texto_obj else SequenceMatcher(None, ventana, texto_obj).ratio()
        if ratio > mejor[0]:
            mejor = (ratio, palabras[i][1])
            if ratio == 1.0:
                break
    return mejor if mejor[0] >= UMBRAL_SIMILITUD else None
