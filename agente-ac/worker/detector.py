"""Detección automática de publicaciones nuevas del canal (feed RSS público de YouTube).

Los directos aparecen en el feed mientras están en curso; solo se encolan cuando terminaron.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from agente.medios import info_youtube
from app.cola import encolar
from app.config import config
from app.db import auditar, conexion

log = logging.getLogger("detector")
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
VENTANA = timedelta(hours=48)  # no procesar el historial antiguo del canal


def entradas_recientes(xml: str, ahora: datetime) -> list[dict]:
    raiz = ET.fromstring(xml)
    salida = []
    for e in raiz.findall("a:entry", NS):
        publicado = datetime.fromisoformat(e.findtext("a:published", namespaces=NS))
        if ahora - publicado <= VENTANA:
            salida.append({"youtube_id": e.findtext("yt:videoId", namespaces=NS),
                           "titulo": e.findtext("a:title", namespaces=NS) or ""})
    return salida


def revisar_canal() -> int:
    cfg = config()
    if not cfg.canal_youtube_id:
        return 0
    r = httpx.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cfg.canal_youtube_id}",
                  proxy=cfg.proxy_youtube or None, timeout=30)
    r.raise_for_status()
    nuevos = 0
    for entrada in entradas_recientes(r.text, datetime.now(timezone.utc)):
        with conexion() as conn:
            if conn.execute("select 1 from videos where youtube_id = %s", (entrada["youtube_id"],)).fetchone():
                continue
        url = f"https://www.youtube.com/watch?v={entrada['youtube_id']}"
        if info_youtube(url, cfg.proxy_youtube or None)["en_vivo"]:
            continue  # se volverá a revisar cuando termine la transmisión
        with conexion() as conn:
            video = conn.execute(
                "insert into videos (origen, url, youtube_id, titulo) values ('youtube', %s, %s, %s) "
                "on conflict (youtube_id) do nothing returning id",
                (url, entrada["youtube_id"], entrada["titulo"]),
            ).fetchone()
            if video:
                encolar(conn, "procesar_video", str(video["id"]))
                auditar(conn, None, "detectar", "video", str(video["id"]), {"titulo": entrada["titulo"]})
                nuevos += 1
    if nuevos:
        log.info("%d publicaciones nuevas encoladas", nuevos)
    return nuevos
