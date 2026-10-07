"""Procesamiento de una entrevista: de la fuente a las piezas propuestas en el panel."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from psycopg.types.json import Jsonb

from agente import diseno
from agente.almacenamiento import Almacenamiento
from agente.analisis import analizar
from agente.medios import Fuente, info_youtube
from agente.transcripcion import transcribir
from agente.verificacion import ubicar_cita
from app.config import config
from app.db import conexion

log = logging.getLogger("pipeline")

# USD por millón de tokens (entrada, salida). Verificar en la página de precios al cambiar de modelo.
PRECIOS = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0)}


def _estado(video_id: str, estado: str, **campos) -> None:
    sets = ", ".join(f"{k} = %s" for k in campos)
    with conexion() as conn:
        conn.execute(f"update videos set estado = %s, actualizado_en = now(){', ' + sets if sets else ''} where id = %s",
                     (estado, *campos.values(), video_id))


def _insertar_pieza(video_id: str, tipo: str, orden: int, contenido: dict, ruta: str | None, verificada: bool) -> None:
    with conexion() as conn:
        conn.execute(
            """insert into piezas (video_id, tipo, orden, contenido, archivo_ruta, cita_verificada)
               values (%s, %s, %s, %s, %s, %s)""",
            (video_id, tipo, orden, Jsonb(contenido), ruta, verificada),
        )


def procesar_video(trabajo: dict) -> dict:
    """Devuelve el consumo de la IA para registrarlo en el trabajo."""
    cfg = config()
    video_id = str(trabajo["video_id"])
    alm = Almacenamiento(cfg.supabase_url, cfg.supabase_service_key)
    carpeta = Path(cfg.carpeta_trabajo) / video_id
    carpeta.mkdir(parents=True, exist_ok=True)

    with conexion() as conn:
        video = conn.execute("select * from videos where id = %s", (video_id,)).fetchone()
        transcripcion = conn.execute("select segmentos from transcripciones where video_id = %s",
                                     (video_id,)).fetchone()
        estilo = conn.execute("select instrucciones from estilo_canal where activo").fetchone()
    _estado(video_id, "procesando", error=None)

    try:
        # 1. Fuente
        if video["origen"] == "youtube":
            info = info_youtube(video["url"], cfg.proxy_youtube or None)
            fuente = Fuente(carpeta, url=video["url"], proxy=cfg.proxy_youtube or None)
            titulo, total = info["titulo"], float(info["duracion_s"] or 0)
        else:
            local = carpeta / Path(video["archivo_ruta"]).name
            if not local.exists():
                alm.descargar(video["archivo_ruta"], local)
            fuente = Fuente(carpeta, archivo=local)
            titulo, total = video["titulo"], diseno.duracion(local)
        _estado(video_id, "procesando", titulo=titulo, duracion_s=total)

        # 2. Transcripción (se reutiliza al regenerar)
        if transcripcion:
            segmentos = transcripcion["segmentos"]
        else:
            log.info("transcribiendo %s", video_id)
            segmentos = transcribir(fuente.audio(), cfg.groq_api_key)
            with conexion() as conn:
                conn.execute(
                    "insert into transcripciones (video_id, proveedor, segmentos, texto) values (%s, 'groq', %s, %s)",
                    (video_id, Jsonb(segmentos), " ".join(s["texto"] for s in segmentos)),
                )

        # 3. Análisis con Claude
        log.info("analizando %s", video_id)
        resultado = analizar(segmentos, titulo, estilo["instrucciones"] if estilo else "", cfg.claude_modelo,
                             trabajo["datos"].get("instruccion", ""))
        a = resultado.analisis
        with conexion() as conn:  # una regeneración reemplaza las propuestas anteriores no aprobadas
            conn.execute("update piezas set estado = 'descartada' where video_id = %s "
                         "and estado in ('propuesta', 'editada')", (video_id,))

        # 4. Titulares con captura (solo los que tienen cita verificada)
        fuente_letra = diseno.buscar_fuente(None)
        for n, t in enumerate(a.titulares, 1):
            ubicacion = ubicar_cita(t.cita_textual, segmentos)
            if not ubicacion:
                log.warning("titular descartado, cita no encontrada: %s", t.cita_textual)
                continue
            t.segundo_captura = ubicacion[1]
            tramo = fuente.tramo(t.segundo_captura - 0.5, t.segundo_captura + 3, f"tramo_titular_{n}")
            foto = diseno.mejor_fotograma(tramo, carpeta)
            imagen = carpeta / f"titular_{n}.jpg"
            diseno.crear_miniatura(foto, t, fuente_letra, imagen)
            ruta = alm.subir(imagen, f"videos/{video_id}/titulares/{trabajo['id']}_{n}.jpg")
            _insertar_pieza(video_id, "titular", n, t.model_dump(), ruta, True)

        # 5. Clips verticales
        for n, c in enumerate(a.clips, 1):
            if not ubicar_cita(c.cita_textual, segmentos):
                log.warning("clip descartado, cita no encontrada: %s", c.cita_textual)
                continue
            ini, fin = diseno.ajustar_a_frases(c.inicio, c.fin, segmentos, total)
            tramo = fuente.tramo(ini, fin, f"tramo_clip_{n}")
            archivo = diseno.crear_clip(tramo, c, n, ini, segmentos, fuente_letra, carpeta / "clips")
            ruta = alm.subir(archivo, f"videos/{video_id}/clips/{trabajo['id']}_{n}.mp4")
            _insertar_pieza(video_id, "clip", n, {**c.model_dump(), "inicio": ini, "fin": fin}, ruta, True)

        # 6. Nota periodística
        _insertar_pieza(video_id, "nota", 1, a.nota.model_dump(), None, False)

        _estado(video_id, "listo", invitado=a.invitado, resumen=a.resumen)
        # TODO semana 3: avisar al gerente por WhatsApp y enviar la constancia por email.
    except Exception as e:
        _estado(video_id, "error", error=str(e)[:1000])
        raise
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    entrada, salida = PRECIOS.get(cfg.claude_modelo, (0.0, 0.0))
    return {"tokens_entrada": resultado.tokens_entrada, "tokens_salida": resultado.tokens_salida,
            "costo_usd": round((resultado.tokens_entrada * entrada + resultado.tokens_salida * salida) / 1e6, 4)}
