"""Migración, cola de trabajos y flujo del panel contra un PostgreSQL real."""
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def test_perfil_se_crea_inactivo_al_registrarse(db_url):
    uid = uuid.uuid4()
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        conn.execute("insert into auth.users (id, email, raw_user_meta_data) values (%s, 'a@b.com', %s)",
                     (uid, Jsonb({"full_name": "Ana"})))
        perfil = conn.execute("select * from perfiles where id = %s", (uid,)).fetchone()
    assert perfil["nombre"] == "Ana" and perfil["rol"] == "produccion" and not perfil["activo"]


def test_cola_toma_reintenta_y_completa(db_url):
    from app.cola import completar, encolar, fallar, tomar_siguiente
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        conn.execute("delete from trabajos")
        tid = encolar(conn, "procesar_video", None, {"x": 1})
        t = tomar_siguiente(conn)
        assert t["id"] == tid and t["estado"] == "en_proceso" and t["intentos"] == 1
        assert tomar_siguiente(conn) is None  # ya está tomado
        assert fallar(conn, t, "falló") is True  # quedan intentos → vuelve a pendiente, programado a futuro
        assert tomar_siguiente(conn) is None
        conn.execute("update trabajos set programado_para = now() where id = %s", (tid,))
        t = tomar_siguiente(conn)
        completar(conn, t["id"], tokens_entrada=10, tokens_salida=5, costo_usd=0.01)
        fila = conn.execute("select estado from trabajos where id = %s", (tid,)).fetchone()
        assert fila["estado"] == "completado"


def test_panel_crea_video_desde_enlace_y_edita_pieza(db_url, monkeypatch):
    monkeypatch.setenv("AUTH_DESACTIVADA", "true")
    from fastapi.testclient import TestClient

    from app.config import config
    config.cache_clear()
    from app.main import app

    cliente = TestClient(app)
    assert cliente.get("/salud").json() == {"ok": True}

    r = cliente.post("/videos/enlace", data={"url": "https://www.youtube.com/watch?v=v7cMNTcEtn4"},
                     follow_redirects=False)
    assert r.status_code == 303
    video_id = r.headers["location"].rsplit("/", 1)[1]
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        assert conn.execute("select origen from videos where id = %s", (video_id,)).fetchone()["origen"] == "youtube"
        assert conn.execute("select count(*) n from trabajos where video_id = %s", (video_id,)).fetchone()["n"] == 1
        pieza = conn.execute(
            "insert into piezas (video_id, tipo, contenido) values (%s, 'titular', %s) returning id",
            (video_id, Jsonb({"titular": "ANTES", "etiqueta": "X", "cita_textual": "c"})),
        ).fetchone()["id"]

    # el mismo enlace no duplica el video
    r2 = cliente.post("/videos/enlace", data={"url": "https://youtu.be/v7cMNTcEtn4"}, follow_redirects=False)
    assert r2.headers["location"].endswith(video_id)

    cliente.post(f"/piezas/{pieza}/editar", data={"campo": "titular", "texto": "DESPUÉS"}, follow_redirects=False)
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        p = conn.execute("select contenido, estado, version from piezas where id = %s", (pieza,)).fetchone()
        auditoria = conn.execute("select count(*) n from auditoria where entidad_id = %s", (str(pieza),)).fetchone()
    assert p["contenido"]["titular"] == "DESPUÉS" and p["estado"] == "editada" and p["version"] == 2
    assert auditoria["n"] == 1

    # las páginas del panel se generan sin errores
    assert cliente.get("/login").status_code == 200
    assert cliente.get("/").status_code == 200
    pagina = cliente.get(f"/videos/{video_id}")
    assert pagina.status_code == 200 and "DESPUÉS" in pagina.text

    assert cliente.post("/videos/enlace", data={"url": "https://example.com"}, follow_redirects=False) \
        .headers["location"].startswith("/?aviso=")
