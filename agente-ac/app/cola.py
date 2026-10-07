"""Cola de trabajos sobre PostgreSQL.

`tomar_siguiente` usa FOR UPDATE SKIP LOCKED: varios trabajadores pueden consumir la cola
a la vez sin tomar el mismo trabajo. Los fallos se reintentan con espera creciente.
"""
from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb


def encolar(conn: psycopg.Connection, tipo: str, video_id: str | None = None, datos: dict | None = None) -> int:
    fila = conn.execute(
        "insert into trabajos (tipo, video_id, datos) values (%s, %s, %s) returning id",
        (tipo, video_id, Jsonb(datos or {})),
    ).fetchone()
    return fila["id"]


def tomar_siguiente(conn: psycopg.Connection) -> dict | None:
    return conn.execute(
        """
        update trabajos set estado = 'en_proceso', intentos = intentos + 1, iniciado_en = now()
        where id = (
            select id from trabajos
            where estado = 'pendiente' and programado_para <= now()
            order by programado_para
            for update skip locked
            limit 1
        )
        returning *
        """
    ).fetchone()


def completar(conn: psycopg.Connection, trabajo_id: int, *, tokens_entrada: int | None = None,
              tokens_salida: int | None = None, costo_usd: float | None = None) -> None:
    conn.execute(
        """update trabajos set estado = 'completado', terminado_en = now(), error = null,
           tokens_entrada = %s, tokens_salida = %s, costo_usd = %s where id = %s""",
        (tokens_entrada, tokens_salida, costo_usd, trabajo_id),
    )


def fallar(conn: psycopg.Connection, trabajo: dict, error: str) -> bool:
    """Registra el error. Devuelve True si se reintentará, False si se agotaron los intentos."""
    reintentar = trabajo["intentos"] < trabajo["max_intentos"]
    conn.execute(
        """update trabajos set estado = %s, error = %s, terminado_en = now(),
           programado_para = now() + make_interval(mins => 2 * power(2, intentos)::int)
           where id = %s""",
        ("pendiente" if reintentar else "fallido", error[-4000:], trabajo["id"]),
    )
    return reintentar
