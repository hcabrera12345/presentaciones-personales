"""Trabajador: consume la cola y revisa el canal periódicamente.  python -m worker.main"""
from __future__ import annotations

import logging
import signal
import time

from app.cola import completar, fallar, tomar_siguiente
from app.db import conexion
from worker.detector import revisar_canal
from worker.pipeline import procesar_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")

TAREAS = {"procesar_video": procesar_video}
ESPERA_S = 5
REVISION_CANAL_S = 600
_seguir = True


def _detener(*_):
    global _seguir
    _seguir = False
    log.info("deteniendo al terminar el trabajo actual…")


def ejecutar_uno() -> bool:
    with conexion() as conn:
        trabajo = tomar_siguiente(conn)
    if not trabajo:
        return False
    log.info("trabajo %s (%s) intento %s", trabajo["id"], trabajo["tipo"], trabajo["intentos"])
    try:
        consumo = TAREAS[trabajo["tipo"]](trabajo) or {}
        with conexion() as conn:
            completar(conn, trabajo["id"], **consumo)
    except Exception as e:
        log.exception("trabajo %s falló", trabajo["id"])
        with conexion() as conn:
            fallar(conn, trabajo, f"{type(e).__name__}: {e}")
    return True


def main() -> None:
    signal.signal(signal.SIGTERM, _detener)
    signal.signal(signal.SIGINT, _detener)
    ultima_revision = 0.0
    log.info("trabajador iniciado")
    while _seguir:
        if time.monotonic() - ultima_revision > REVISION_CANAL_S:
            ultima_revision = time.monotonic()
            try:
                revisar_canal()
            except Exception:
                log.exception("no se pudo revisar el canal")
        if not ejecutar_uno():
            time.sleep(ESPERA_S)


if __name__ == "__main__":
    main()
