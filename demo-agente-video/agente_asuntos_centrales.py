#!/usr/bin/env python3
"""
Agente de IA para el canal "Asuntos Centrales".

Toma una entrevista (URL de YouTube o archivo local) y entrega:
  * 5 propuestas de titular "picante" con su captura de pantalla estilo noticia (1280x720)
  * 3 clips cortos verticales (1080x1920) con el mismo estilo y subtítulos animados
  * un reporte HTML para mostrar los resultados en vivo

Pasos del agente:
  1. Obtener el video (yt-dlp si es URL)
  2. Transcribir con marcas de tiempo por palabra (faster-whisper, local)
  3. Analizar la transcripción con Claude: titulares + momentos para clips
  4. Elegir el mejor fotograma y componer las miniaturas (Pillow)
  5. Cortar y montar los clips verticales (ffmpeg)
  6. Publicar un reporte HTML

Cada paso guarda su resultado en la carpeta de salida; si se vuelve a ejecutar,
reutiliza lo ya hecho (útil para tener la demo "pre-cocinada" como respaldo).

Uso:
  python agente_asuntos_centrales.py "https://www.youtube.com/watch?v=XXXX"
  python agente_asuntos_centrales.py entrevista.mp4 --salida salida/entrevista
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
from pydantic import BaseModel, Field

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # aviso inofensivo en Windows

CANAL = "ASUNTOS CENTRALES"
MODELO = "claude-opus-5-5"

# Paleta "noticia de última hora"
ROJO = (214, 20, 32)
AMARILLO = (255, 214, 0)
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def paso(n: int, texto: str) -> None:
    print(f"\n\033[1;31m▶ PASO {n}\033[0m \033[1m{texto}\033[0m", flush=True)


def info(texto: str) -> None:
    print(f"   · {texto}", flush=True)


def mmss(segundos: float) -> str:
    s = int(round(segundos))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def ejecutar(cmd: list[str], cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Error ejecutando {cmd[0]}:\n{r.stderr[-2000:]}")


def duracion_video(video: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


FUENTES_CANDIDATAS = [
    # Linux
    "/usr/share/fonts/opentype/inter/Inter-Black.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # Windows
    "C:/Windows/Fonts/ariblk.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/Library/Fonts/Arial Black.ttf",
]


def buscar_fuente(preferida: str | None) -> Path:
    for f in ([preferida] if preferida else []) + FUENTES_CANDIDATAS:
        if f and Path(f).exists():
            return Path(f)
    sys.exit("No encontré una fuente gruesa. Usa --fuente /ruta/a/fuente.ttf")


# --------------------------------------------------------------------------- #
# Paso 1: obtener el video
# --------------------------------------------------------------------------- #
def obtener_video(fuente: str, salida: Path) -> tuple[Path, str]:
    if Path(fuente).exists():
        return Path(fuente).resolve(), Path(fuente).stem

    existentes = list(salida.glob("video.*"))
    titulo_txt = salida / "titulo_original.txt"
    if existentes and titulo_txt.exists():
        info("video ya descargado, lo reutilizo")
        return existentes[0], titulo_txt.read_text(encoding="utf-8")

    info("descargando con yt-dlp…")
    ejecutar([
        sys.executable, "-m", "yt_dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4", "-o", str(salida / "video.%(ext)s"),
        "--print-to-file", "%(title)s", str(titulo_txt), "--no-playlist", fuente,
    ])
    return next(salida.glob("video.*")), titulo_txt.read_text(encoding="utf-8").strip()


# --------------------------------------------------------------------------- #
# Paso 2: transcribir
# --------------------------------------------------------------------------- #
def transcribir(video: Path, salida: Path, modelo_whisper: str, idioma: str, gpu: bool = False) -> list[dict]:
    archivo = salida / "transcripcion.json"
    if archivo.exists():
        info("transcripción ya existe, la reutilizo")
        return json.loads(archivo.read_text(encoding="utf-8"))

    from faster_whisper import WhisperModel

    info(f"transcribiendo con Whisper '{modelo_whisper}' (puede tardar)…")
    # Por defecto CPU: con device="auto" se intenta usar una tarjeta NVIDIA aunque falten las
    # librerías CUDA (cublas64_12.dll) y la transcripción falla. --gpu solo si CUDA está instalado.
    modelo = WhisperModel(modelo_whisper, device="cuda" if gpu else "cpu",
                          compute_type="float16" if gpu else "int8")
    segmentos_it, _ = modelo.transcribe(str(video), language=idioma, word_timestamps=True, vad_filter=True)
    segmentos = []
    total = duracion_video(video)
    for s in segmentos_it:
        segmentos.append({
            "inicio": round(s.start, 2), "fin": round(s.end, 2), "texto": s.text.strip(),
            "palabras": [{"inicio": round(w.start, 2), "fin": round(w.end, 2), "p": w.word.strip()}
                         for w in (s.words or [])],
        })
        print(f"\r   · {mmss(s.end)} / {mmss(total)} transcrito", end="", flush=True)
    print()
    archivo.write_text(json.dumps(segmentos, ensure_ascii=False, indent=1), encoding="utf-8")
    return segmentos


# --------------------------------------------------------------------------- #
# Paso 3: análisis con Claude
# --------------------------------------------------------------------------- #
class Titular(BaseModel):
    etiqueta: str = Field(description="Cintillo rojo corto en mayúsculas: 'ÚLTIMA HORA', 'EXCLUSIVO', 'POLÉMICA', 'REVELA', 'ALERTA'…")
    titular: str = Field(description="Titular picante, máximo 70 caracteres, en mayúsculas")
    palabra_clave: str = Field(description="1 a 3 palabras EXACTAS del titular que se resaltan en amarillo")
    cita_textual: str = Field(description="Frase literal de la transcripción que respalda el titular")
    segundo_captura: float = Field(description="Segundo del video donde el entrevistado dice la cita (para la captura)")
    por_que_funciona: str = Field(description="Una línea: por qué este titular engancha")


class Clip(BaseModel):
    titulo_gancho: str = Field(description="Gancho del clip en mayúsculas, máximo 55 caracteres")
    palabra_clave: str = Field(description="1 a 2 palabras EXACTAS del gancho que se resaltan en amarillo")
    inicio: float = Field(description="Segundo de inicio (al comienzo de una frase)")
    fin: float = Field(description="Segundo de fin (al terminar una idea); duración entre 20 y 60 s")
    por_que_funciona: str = Field(description="Una línea: por qué este momento funciona como short/reel")


class Analisis(BaseModel):
    invitado: str = Field(description="Nombre y cargo del entrevistado si se menciona; si no, 'Invitado'")
    resumen: str = Field(description="Resumen de la entrevista en 2 frases")
    titulares: list[Titular] = Field(description="Exactamente 5 titulares, del más fuerte al menos fuerte")
    clips: list[Clip] = Field(description="Exactamente 3 clips que no se solapen")


SISTEMA = f"""Eres el editor digital del canal de YouTube de noticias y análisis "{CANAL}".
Tu trabajo: convertir entrevistas largas en titulares y clips que la gente quiera abrir y compartir.

Estilo del canal:
- Titulares de noticia de última hora: directos, en mayúsculas, con tensión, conflicto o revelación.
- Verbos fuertes (REVELA, ADVIERTE, ROMPE EL SILENCIO, ARREMETE, CONFIESA, DENUNCIA).
- Nombra a la persona o institución cuando eso le dé fuerza al titular.
- Cifras y datos concretos siempre que existan en la entrevista.

Regla innegociable — picante pero verdadero:
- Cada titular y cada clip debe estar respaldado por algo que el entrevistado DIJO LITERALMENTE.
- No inventes hechos, no pongas en boca del invitado lo que no dijo, no exageres cifras.
- Puedes usar comillas para citar, pero solo con palabras textuales.

Para los clips:
- Busca momentos autosuficientes (se entienden sin contexto), con una idea fuerte o una frase memorable.
- Que empiecen al inicio de una frase y terminen cuando la idea se cierra; entre 20 y 60 segundos.
- Los 3 clips deben ser de momentos distintos de la entrevista.
"""


def analizar(segmentos: list[dict], titulo_original: str, salida: Path) -> Analisis:
    archivo = salida / "analisis.json"
    if archivo.exists():
        info("análisis ya existe, lo reutilizo (borra analisis.json para regenerar)")
        return Analisis.model_validate_json(archivo.read_text(encoding="utf-8"))

    import anthropic

    transcripcion = "\n".join(f"[{s['inicio']:.1f}s] {s['texto']}" for s in segmentos)
    info(f"enviando {len(segmentos)} segmentos a Claude ({MODELO})…")
    cliente = anthropic.Anthropic()
    t0 = time.time()
    respuesta = cliente.beta.messages.parse(
        model=MODELO,
        max_tokens=16000,
        system=SISTEMA,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        # Si el modelo principal declina, el servidor reintenta con otro modelo adecuado
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": (
                f"Título original del video: {titulo_original}\n\n"
                f"<transcripcion>\n{transcripcion}\n</transcripcion>\n\n"
                "Propón 5 titulares con su momento para la captura y 3 clips cortos."
            ),
        }],
        output_format=Analisis,
    )
    if respuesta.stop_reason == "refusal":
        sys.exit("Claude declinó analizar este contenido.")
    analisis = respuesta.parsed_output
    info(f"listo en {time.time() - t0:.0f}s")
    archivo.write_text(analisis.model_dump_json(indent=2), encoding="utf-8")
    return analisis


# --------------------------------------------------------------------------- #
# Paso 4: capturas estilo noticia
# --------------------------------------------------------------------------- #
def extraer_fotograma(video: Path, segundo: float, destino: Path) -> Image.Image:
    ejecutar(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(segundo, 0):.2f}", "-i", str(video),
              "-frames:v", "1", "-q:v", "2", str(destino)])
    return Image.open(destino).convert("RGB")


def nitidez(img: Image.Image) -> float:
    gris = img.convert("L").resize((320, 180))
    brillo = ImageStat.Stat(gris).mean[0]
    if brillo < 25:  # fotograma negro o transición
        return 0
    return ImageStat.Stat(gris.filter(ImageFilter.FIND_EDGES)).var[0]


def mejor_fotograma(video: Path, segundo: float, tmp: Path, duracion: float) -> Image.Image:
    """Prueba varios instantes alrededor de la cita y se queda con el más nítido (evita ojos cerrados/borrosos)."""
    candidatos = []
    for i, d in enumerate((-1.0, -0.5, 0, 0.5, 1.0, 1.5)):
        t = min(max(segundo + d, 0), max(duracion - 0.5, 0))
        img = extraer_fotograma(video, t, tmp / f"cand_{i}.jpg")
        candidatos.append((nitidez(img), img))
    return max(candidatos, key=lambda c: c[0])[1]


def cubrir(img: Image.Image, ancho: int, alto: int) -> Image.Image:
    escala = max(ancho / img.width, alto / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    x, y = (img.width - ancho) // 2, (img.height - alto) // 2
    return img.crop((x, y, x + ancho, y + alto))


def partir_lineas(texto: str, fuente: ImageFont.FreeTypeFont, ancho_max: int) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if fuente.getlength(prueba) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    return lineas + ([actual] if actual else [])


def normalizar(p: str) -> str:
    return re.sub(r"[^\wáéíóúüñ]", "", p.lower())


def dibujar_titular(draw: ImageDraw.ImageDraw, texto: str, clave: str, ruta_fuente: Path,
                    caja: tuple[int, int, int, int], tam_max: int, max_lineas: int) -> None:
    """Escribe el titular dentro de la caja, ajustando el tamaño y resaltando la palabra clave en amarillo."""
    x0, y0, x1, y1 = caja
    claves = {normalizar(p) for p in clave.split()}
    tam = tam_max
    while True:
        fuente = ImageFont.truetype(str(ruta_fuente), tam)
        lineas = partir_lineas(texto.upper(), fuente, x1 - x0)
        alto_linea = int(tam * 1.08)
        if (len(lineas) <= max_lineas and alto_linea * len(lineas) <= y1 - y0) or tam <= 28:
            break
        tam -= 4
    y = y1 - alto_linea * len(lineas)  # alineado abajo
    for linea in lineas:
        x = x0
        for palabra in linea.split():
            color = AMARILLO if normalizar(palabra) in claves else BLANCO
            draw.text((x + 4, y + 5), palabra, font=fuente, fill=NEGRO)  # sombra
            draw.text((x, y), palabra, font=fuente, fill=color, stroke_width=max(2, tam // 22), stroke_fill=NEGRO)
            x += fuente.getlength(palabra + " ")
        y += alto_linea


def dibujar_cintillo(draw: ImageDraw.ImageDraw, texto: str, ruta_fuente: Path, x: int, y: int, tam: int) -> int:
    fuente = ImageFont.truetype(str(ruta_fuente), tam)
    pad = tam // 2
    ancho = int(fuente.getlength(texto.upper())) + 2 * pad
    draw.rectangle((x, y, x + ancho, y + tam + pad), fill=ROJO)
    draw.text((x + pad, y + pad // 2 - tam // 10), texto.upper(), font=fuente, fill=BLANCO)
    return ancho


def dibujar_marca(draw: ImageDraw.ImageDraw, ruta_fuente: Path, ancho_lienzo: int, y: int, tam: int) -> None:
    fuente = ImageFont.truetype(str(ruta_fuente), tam)
    pad = tam // 2
    ancho = int(fuente.getlength(CANAL)) + 2 * pad
    x = ancho_lienzo - ancho - pad * 2
    draw.rectangle((x, y, x + ancho, y + tam + pad), fill=BLANCO)
    draw.rectangle((x, y + tam + pad, x + ancho, y + tam + pad + tam // 5), fill=ROJO)
    draw.text((x + pad, y + pad // 2 - tam // 10), CANAL, font=fuente, fill=NEGRO)


def degradado_inferior(lienzo: Image.Image, desde: float, opacidad_max: int = 235) -> None:
    ancho, alto = lienzo.size
    mascara = Image.new("L", (1, alto))
    inicio = int(alto * desde)
    for y in range(alto):
        mascara.putpixel((0, y), 0 if y < inicio else int(opacidad_max * ((y - inicio) / (alto - inicio)) ** 0.8))
    lienzo.paste(Image.new("RGB", lienzo.size, NEGRO), (0, 0), mascara.resize(lienzo.size))


def crear_miniatura(foto: Image.Image, t: Titular, ruta_fuente: Path, destino: Path) -> None:
    W, H = 1280, 720
    lienzo = cubrir(foto, W, H)
    degradado_inferior(lienzo, desde=0.35)
    d = ImageDraw.Draw(lienzo)
    dibujar_marca(d, ruta_fuente, W, 28, 30)
    dibujar_cintillo(d, t.etiqueta, ruta_fuente, 48, 330, 38)
    dibujar_titular(d, t.titular, t.palabra_clave, ruta_fuente, (48, 395, W - 48, H - 70), 86, 3)
    # Barra inferior tipo noticiero
    d.rectangle((0, H - 46, W, H), fill=ROJO)
    f = ImageFont.truetype(str(ruta_fuente), 22)
    cita = "«" + t.cita_textual.strip(' «»"') + "»"
    while f.getlength(cita) > W - 96 and len(cita) > 10:
        cita = cita[:-5].rstrip() + "…»"
    d.text((48, H - 38), cita, font=f, fill=BLANCO)
    lienzo.save(destino, quality=92)


# --------------------------------------------------------------------------- #
# Paso 5: clips verticales
# --------------------------------------------------------------------------- #
def ajustar_a_frases(clip: Clip, segmentos: list[dict], duracion: float) -> tuple[float, float]:
    """Mueve el inicio/fin a los bordes de frase más cercanos para no cortar a mitad de palabra."""
    ini = min(segmentos, key=lambda s: abs(s["inicio"] - clip.inicio))["inicio"]
    fin = min(segmentos, key=lambda s: abs(s["fin"] - clip.fin))["fin"]
    if fin - ini < 10:
        fin = min(ini + 30, duracion)
    fin = min(fin, ini + 75, duracion)
    return max(ini - 0.15, 0), min(fin + 0.35, duracion)


def ass_tiempo(t: float) -> str:
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def crear_subtitulos(segmentos: list[dict], ini: float, fin: float, nombre_fuente: str, destino: Path) -> None:
    """Subtítulos de 3 palabras con la palabra que se está diciendo resaltada en amarillo (estilo shorts)."""
    palabras = [w for s in segmentos for w in s.get("palabras", []) if w["fin"] > ini and w["inicio"] < fin]
    if not palabras:  # transcripción sin marcas por palabra: usar frases completas
        palabras = [{"inicio": s["inicio"], "fin": s["fin"], "p": s["texto"]}
                    for s in segmentos if s["fin"] > ini and s["inicio"] < fin]

    grupos, actual = [], []
    for w in palabras:
        if actual and (len(actual) >= 3 or w["inicio"] - actual[-1]["fin"] > 0.6
                       or re.search(r"[.?!]$", actual[-1]["p"])):
            grupos.append(actual)
            actual = []
        actual.append(w)
    if actual:
        grupos.append(actual)

    eventos = []
    for g in grupos:
        for i, w in enumerate(g):
            t0 = w["inicio"] - ini
            t1 = (g[i + 1]["inicio"] if i + 1 < len(g) else w["fin"]) - ini
            texto = " ".join(
                ("{\\c&H00D6FF&\\fscx110\\fscy110}" + x["p"].upper() + "{\\c&HFFFFFF&\\fscx100\\fscy100}")
                if j == i else x["p"].upper()
                for j, x in enumerate(g)
            )
            eventos.append(f"Dialogue: 0,{ass_tiempo(t0)},{ass_tiempo(t1)},Sub,,0,0,0,,{texto}")

    destino.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{nombre_fuente},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,7,4,2,60,60,470,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(eventos) + "\n", encoding="utf-8")


def crear_capa_clip(c: Clip, numero: int, ruta_fuente: Path, destino: Path) -> None:
    """PNG transparente 1080x1920 con cintillo, gancho, marca del canal y barra inferior."""
    W, H = 1080, 1920
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    d.rectangle((0, 0, W, 610), fill=(0, 0, 0, 200))
    dibujar_marca(d, ruta_fuente, W, 70, 40)
    dibujar_cintillo(d, f"CLIP {numero}", ruta_fuente, 60, 160, 44)
    dibujar_titular(d, c.titulo_gancho, c.palabra_clave, ruta_fuente, (60, 240, W - 60, 590), 92, 3)
    d.rectangle((0, H - 120, W, H), fill=ROJO + (255,))
    texto = "VER LA ENTREVISTA COMPLETA EN EL CANAL"
    tam = 40
    while ImageFont.truetype(str(ruta_fuente), tam).getlength(texto) > W - 80:
        tam -= 2
    f = ImageFont.truetype(str(ruta_fuente), tam)
    d.text(((W - f.getlength(texto)) / 2, H - 88), texto, font=f, fill=BLANCO)
    capa.save(destino)


def crear_clip(video: Path, c: Clip, numero: int, segmentos: list[dict], ruta_fuente: Path,
               nombre_fuente: str, carpeta: Path, duracion: float) -> tuple[float, float]:
    ini, fin = ajustar_a_frases(c, segmentos, duracion)
    crear_subtitulos(segmentos, ini, fin, nombre_fuente, carpeta / f"clip_{numero}.ass")
    crear_capa_clip(c, numero, ruta_fuente, carpeta / f"clip_{numero}_capa.png")
    filtro = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[fondo];"
        "[b]scale=1080:-2[frente];"
        "[fondo][frente]overlay=(W-w)/2:690[base];"
        "[base][1:v]overlay=0:0[conmarca];"
        f"[conmarca]ass=clip_{numero}.ass:fontsdir=fuentes[v]"
    )
    # Se ejecuta dentro de la carpeta para usar rutas relativas en el filtro (evita problemas de escape en Windows)
    ejecutar([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ini:.2f}", "-t", f"{fin - ini:.2f}",
        "-i", str(video.resolve()), "-i", f"clip_{numero}_capa.png",
        "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", f"clip_{numero}.mp4",
    ], cwd=carpeta)
    return ini, fin


# --------------------------------------------------------------------------- #
# Paso 6: reporte HTML
# --------------------------------------------------------------------------- #
def crear_reporte(a: Analisis, titulo: str, rangos: list[tuple[float, float]], destino: Path) -> None:
    e = html.escape
    tarjetas = "".join(f"""
      <article class="card">
        <img src="titulares/titular_{i}.jpg" alt="">
        <div class="pad"><span class="tag">{e(t.etiqueta)}</span>
          <h3>{e(t.titular)}</h3>
          <p class="cita">«{e(t.cita_textual)}» <span class="t">{mmss(t.segundo_captura)}</span></p>
          <p class="why">{e(t.por_que_funciona)}</p></div>
      </article>""" for i, t in enumerate(a.titulares, 1))
    clips = "".join(f"""
      <article class="card clip">
        <video src="clips/clip_{i}.mp4" controls preload="metadata"></video>
        <div class="pad"><span class="tag">CLIP {i} · {mmss(r[0])}–{mmss(r[1])} · {r[1] - r[0]:.0f}s</span>
          <h3>{e(c.titulo_gancho)}</h3><p class="why">{e(c.por_que_funciona)}</p></div>
      </article>""" for i, (c, r) in enumerate(zip(a.clips, rangos), 1))
    destino.write_text(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{CANAL} · Agente IA</title>
<style>
:root{{--bg:#0d0d0f;--card:#18181c;--txt:#f3f3f3;--mut:#a5a5ad;--rojo:#d61420;--amar:#ffd600}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font:16px/1.45 system-ui,sans-serif}}
header{{background:var(--rojo);padding:20px 24px}}header b{{background:#fff;color:#000;padding:4px 10px;font-weight:900}}
header h1{{margin:12px 0 4px;font-size:clamp(22px,4vw,34px)}}header p{{margin:0;opacity:.9}}
main{{max-width:1280px;margin:auto;padding:24px 16px}}h2{{border-left:6px solid var(--amar);padding-left:10px}}
.grid{{display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}}
.card{{background:var(--card);border-radius:10px;overflow:hidden}}.card img{{width:100%;display:block}}
.pad{{padding:14px 16px}}.tag{{background:var(--rojo);color:#fff;font-weight:800;font-size:12px;padding:3px 8px}}
.card h3{{margin:10px 0 6px;text-transform:uppercase}}.cita{{color:var(--amar);margin:0 0 6px}}.t{{color:var(--mut);font-size:13px}}
.why{{color:var(--mut);margin:0;font-size:14px}}.clip video{{width:100%;aspect-ratio:9/16;background:#000;display:block}}
.clips{{grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}}
</style></head><body>
<header><b>{CANAL}</b><h1>{e(titulo)}</h1><p>{e(a.invitado)} — {e(a.resumen)}</p></header>
<main><h2>5 titulares propuestos</h2><section class="grid">{tarjetas}</section>
<h2>3 clips cortos</h2><section class="grid clips">{clips}</section></main></body></html>""", encoding="utf-8")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Agente IA de titulares y clips para Asuntos Centrales")
    ap.add_argument("fuente", help="URL de YouTube o ruta a un archivo de video")
    ap.add_argument("--salida", help="carpeta de salida (por defecto salida/<nombre>)")
    ap.add_argument("--whisper", default="small", help="modelo Whisper: tiny, base, small, medium, large-v3")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--gpu", action="store_true", help="transcribir con GPU NVIDIA (requiere CUDA 12 y cuDNN)")
    ap.add_argument("--fuente-letra", dest="fuente_letra", help="ruta a una fuente .ttf/.otf gruesa")
    args = ap.parse_args()

    nombre = re.sub(r"[^\w-]+", "_", Path(args.fuente).stem if Path(args.fuente).exists()
                    else args.fuente.split("v=")[-1].split("/")[-1])[:40]
    salida = Path(args.salida or Path("salida") / nombre)
    for sub in ("titulares", "clips/fuentes", "tmp"):
        (salida / sub).mkdir(parents=True, exist_ok=True)

    ruta_fuente = buscar_fuente(args.fuente_letra)
    shutil.copy(ruta_fuente, salida / "clips/fuentes" / ruta_fuente.name)
    nombre_fuente = ImageFont.truetype(str(ruta_fuente), 10).getname()[0]
    t_total = time.time()

    paso(1, "Obtener el video")
    video, titulo = obtener_video(args.fuente, salida)
    duracion = duracion_video(video)
    info(f"{titulo} — {mmss(duracion)}")

    paso(2, "Transcribir la entrevista")
    segmentos = transcribir(video, salida, args.whisper, args.idioma, args.gpu)
    info(f"{len(segmentos)} frases, {sum(len(s['texto'].split()) for s in segmentos)} palabras")

    paso(3, "Claude analiza la entrevista y propone titulares y clips")
    a = analizar(segmentos, titulo, salida)
    info(f"invitado: {a.invitado}")
    for i, t in enumerate(a.titulares, 1):
        print(f"   {i}. [{t.etiqueta}] {t.titular}  ({mmss(t.segundo_captura)})")

    paso(4, "Elegir fotogramas y diseñar las 5 capturas estilo noticia")
    for i, t in enumerate(a.titulares[:5], 1):
        foto = mejor_fotograma(video, t.segundo_captura, salida / "tmp", duracion)
        crear_miniatura(foto, t, ruta_fuente, salida / "titulares" / f"titular_{i}.jpg")
        info(f"titulares/titular_{i}.jpg")

    paso(5, "Cortar y montar los 3 clips verticales")
    rangos = []
    for i, c in enumerate(a.clips[:3], 1):
        rango = crear_clip(video, c, i, segmentos, ruta_fuente, nombre_fuente, salida / "clips", duracion)
        rangos.append(rango)
        info(f"clips/clip_{i}.mp4  ({mmss(rango[0])}–{mmss(rango[1])})  {c.titulo_gancho}")

    paso(6, "Publicar reporte")
    crear_reporte(a, titulo, rangos, salida / "reporte.html")
    shutil.rmtree(salida / "tmp", ignore_errors=True)
    print(f"\n\033[1;32m✔ Listo en {time.time() - t_total:.0f}s →\033[0m {(salida / 'reporte.html').resolve()}")


if __name__ == "__main__":
    main()
