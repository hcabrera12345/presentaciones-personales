"""Las pruebas de base de datos usan TEST_DATABASE_URL (un PostgreSQL desechable).
Sin esa variable se omiten; el resto de pruebas no necesita servicios externos."""
import os
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no definida")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade; drop schema if exists auth cascade; "
                     "drop schema if exists storage cascade; create schema public;")
        conn.execute((RAIZ / "tests/supabase_stub.sql").read_text())
        for migracion in sorted((RAIZ / "supabase/migrations").glob("*.sql")):
            conn.execute(migracion.read_text())
    os.environ["DATABASE_URL"] = url
    from app.config import config
    config.cache_clear()
    return url
