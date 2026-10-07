"""Conexión a PostgreSQL (Supabase) con un pool compartido."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import config

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(config().database_url, min_size=1, max_size=5,
                               kwargs={"row_factory": dict_row, "autocommit": False}, open=True)
    return _pool


@contextmanager
def conexion() -> Iterator[psycopg.Connection]:
    """Una transacción: confirma al salir sin errores, revierte si hay excepción."""
    with pool().connection() as conn:
        yield conn


def auditar(conn: psycopg.Connection, usuario_id: str | None, accion: str, entidad: str,
            entidad_id: str | None = None, detalle: dict | None = None) -> None:
    conn.execute(
        "insert into auditoria (usuario_id, accion, entidad, entidad_id, detalle) values (%s, %s, %s, %s, %s)",
        (usuario_id, accion, entidad, entidad_id, psycopg.types.json.Jsonb(detalle or {})),
    )
