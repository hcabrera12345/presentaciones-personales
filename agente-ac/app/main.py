"""Panel web interno y API del agente."""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.types.json import Jsonb

from agente.almacenamiento import Almacenamiento
from app.auth import NoAutenticado, Usuario, usuario_actual
from app.cola import encolar
from app.config import config
from app.db import auditar, conexion

app = FastAPI(title="Agente IA · Asuntos Centrales", docs_url=None, redoc_url=None)
plantillas = Jinja2Templates(directory=Path(__file__).parent / "templates")
UsuarioActual = Annotated[Usuario, Depends(usuario_actual)]

PATRON_YOUTUBE = re.compile(r"(?:youtube\.com/(?:watch\?v=|live/|shorts/)|youtu\.be/)([\w-]{11})")


def almacenamiento() -> Almacenamiento:
    cfg = config()
    return Almacenamiento(cfg.supabase_url, cfg.supabase_service_key)


@app.exception_handler(NoAutenticado)
def _sin_sesion(request: Request, exc: NoAutenticado):
    return RedirectResponse("/login", status_code=303)


@app.get("/salud")
def salud() -> dict:
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login(request: Request):
    cfg = config()
    return plantillas.TemplateResponse(request, "login.html",
                                       {"supabase_url": cfg.supabase_url, "supabase_anon_key": cfg.supabase_anon_key})


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, usuario: UsuarioActual, aviso: str = ""):
    with conexion() as conn:
        videos = conn.execute(
            "select id, titulo, origen, estado, invitado, creado_en, error from videos order by creado_en desc limit 50"
        ).fetchall()
    return plantillas.TemplateResponse(request, "inicio.html", {"usuario": usuario, "videos": videos, "aviso": aviso})


@app.post("/videos/enlace")
def nuevo_enlace(usuario: UsuarioActual, url: Annotated[str, Form()], solo_analisis: Annotated[bool, Form()] = False):
    coincidencia = PATRON_YOUTUBE.search(url)
    if not coincidencia:
        return RedirectResponse("/?aviso=Por+ahora+solo+se+aceptan+enlaces+de+YouTube", status_code=303)
    youtube_id = coincidencia.group(1)
    with conexion() as conn:
        existente = conn.execute("select id from videos where youtube_id = %s", (youtube_id,)).fetchone()
        if existente:
            return RedirectResponse(f"/videos/{existente['id']}", status_code=303)
        video = conn.execute(
            """insert into videos (origen, url, youtube_id, solo_analisis, creado_por)
               values ('youtube', %s, %s, %s, %s) returning id""",
            (f"https://www.youtube.com/watch?v={youtube_id}", youtube_id, solo_analisis, usuario.id),
        ).fetchone()
        encolar(conn, "procesar_video", str(video["id"]))
        auditar(conn, usuario.id, "crear", "video", str(video["id"]), {"url": url})
    return RedirectResponse(f"/videos/{video['id']}", status_code=303)


@app.post("/videos/archivo")
def nuevo_archivo(usuario: UsuarioActual, archivo: UploadFile):
    # Archivos grandes (streamings completos) deberían subirse directo del navegador a Storage
    # con subida reanudable; este camino sirve para videos de tamaño moderado.
    with conexion() as conn:
        video = conn.execute(
            "insert into videos (origen, titulo, creado_por) values ('archivo', %s, %s) returning id",
            (Path(archivo.filename or "video").stem, usuario.id),
        ).fetchone()
        video_id = str(video["id"])
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / (archivo.filename or "video.mp4")
            with local.open("wb") as f:
                shutil.copyfileobj(archivo.file, f)
            ruta = almacenamiento().subir(local, f"videos/{video_id}/original{local.suffix}")
        conn.execute("update videos set archivo_ruta = %s where id = %s", (ruta, video_id))
        encolar(conn, "procesar_video", video_id)
        auditar(conn, usuario.id, "crear", "video", video_id, {"archivo": archivo.filename})
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


@app.get("/videos/{video_id}", response_class=HTMLResponse)
def ver_video(request: Request, video_id: str, usuario: UsuarioActual):
    with conexion() as conn:
        video = conn.execute("select * from videos where id = %s", (video_id,)).fetchone()
        if not video:
            raise HTTPException(404)
        piezas = conn.execute(
            "select * from piezas where video_id = %s and estado <> 'descartada' order by tipo, orden",
            (video_id,),
        ).fetchall()
    alm = almacenamiento()
    for p in piezas:
        p["url"] = alm.url_firmada(p["archivo_ruta"]) if p["archivo_ruta"] else None
    return plantillas.TemplateResponse(request, "video.html", {"usuario": usuario, "video": video, "piezas": piezas})


@app.post("/videos/{video_id}/regenerar")
def regenerar(video_id: str, usuario: UsuarioActual, instruccion: Annotated[str, Form()] = ""):
    with conexion() as conn:
        conn.execute("update videos set estado = 'en_cola', error = null where id = %s", (video_id,))
        encolar(conn, "procesar_video", video_id, {"instruccion": instruccion})
        auditar(conn, usuario.id, "regenerar", "video", video_id, {"instruccion": instruccion})
    return RedirectResponse(f"/videos/{video_id}", status_code=303)


@app.post("/piezas/{pieza_id}/editar")
def editar_pieza(pieza_id: str, usuario: UsuarioActual, campo: Annotated[str, Form()], texto: Annotated[str, Form()]):
    if campo not in ("titular", "titulo_gancho", "texto_facebook", "cuerpo"):
        raise HTTPException(400, "Campo no editable")
    with conexion() as conn:
        pieza = conn.execute("select * from piezas where id = %s", (pieza_id,)).fetchone()
        if not pieza:
            raise HTTPException(404)
        contenido = {**pieza["contenido"], campo: texto}
        conn.execute(
            """update piezas set contenido = %s, estado = 'editada', version = version + 1,
               editado_por = %s, actualizado_en = now() where id = %s""",
            (Jsonb(contenido), usuario.id, pieza_id),
        )
        auditar(conn, usuario.id, "editar", "pieza", pieza_id,
                {"campo": campo, "antes": pieza["contenido"].get(campo), "despues": texto})
    return RedirectResponse(f"/videos/{pieza['video_id']}", status_code=303)


@app.post("/piezas/{pieza_id}/descartar")
def descartar_pieza(pieza_id: str, usuario: UsuarioActual):
    with conexion() as conn:
        pieza = conn.execute(
            "update piezas set estado = 'descartada', editado_por = %s, actualizado_en = now() "
            "where id = %s returning video_id", (usuario.id, pieza_id),
        ).fetchone()
        if not pieza:
            raise HTTPException(404)
        auditar(conn, usuario.id, "descartar", "pieza", pieza_id)
    return RedirectResponse(f"/videos/{pieza['video_id']}", status_code=303)


# ───────── WhatsApp (semana 3): verificación del webhook de Meta ─────────
@app.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def verificar_webhook(modo: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
                      desafio: str = Query("", alias="hub.challenge")):
    cfg = config()
    if modo == "subscribe" and cfg.whatsapp_verify_token and token == cfg.whatsapp_verify_token:
        return desafio
    raise HTTPException(403)


@app.post("/webhooks/whatsapp")
async def recibir_whatsapp(request: Request):
    # TODO semana 3: validar la firma X-Hub-Signature-256 y procesar las respuestas
    # (Aprobar / Cambios / Rechazar) con integraciones.whatsapp.procesar_respuesta.
    await request.body()
    return {"ok": True}
