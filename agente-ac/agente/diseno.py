"""Diseño de piezas con la identidad del canal: capturas estilo noticia y clips verticales.

Las funciones de dibujo vienen del agente de la demo (validado con el cliente). Aquí se
adaptan para trabajar con "tramos": fragmentos cortos del video, que es lo único que se
descarga de YouTube para ahorrar ancho de banda del proxy.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from agente.modelos import Clip, Titular

CANAL = "ASUNTOS CENTRALES"

# Paleta "noticia de última hora"
ROJO = (214, 20, 32)
AMARILLO = (255, 214, 0)
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)


def ejecutar(cmd: list[str], cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Falló {cmd[0]}: {r.stderr[-2000:]}")


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
    raise FileNotFoundError("No hay una fuente gruesa instalada (ver FUENTES_CANDIDATAS o FUENTE_LETRA)")


# --------------------------------------------------------------------------- #
# Paso 1: obtener el video

def nitidez(img: Image.Image) -> float:
    gris = img.convert("L").resize((320, 180))
    brillo = ImageStat.Stat(gris).mean[0]
    if brillo < 25:  # fotograma negro o transición
        return 0
    return ImageStat.Stat(gris.filter(ImageFilter.FIND_EDGES)).var[0]



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




# --------------------------------------------------------------------------- #
# Capturas y clips a partir de tramos
# --------------------------------------------------------------------------- #
def duracion(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def mejor_fotograma(tramo: Path, tmp: Path) -> Image.Image:
    """Prueba varios instantes del tramo y se queda con el más nítido (evita ojos cerrados o desenfoque)."""
    largo = duracion(tramo)
    candidatos = []
    for i in range(6):
        t = largo * (i + 1) / 7
        destino = tmp / f"cand_{i}.jpg"
        ejecutar(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(tramo),
                  "-frames:v", "1", "-q:v", "2", str(destino)])
        img = Image.open(destino).convert("RGB")
        candidatos.append((nitidez(img), img))
    return max(candidatos, key=lambda c: c[0])[1]


def ajustar_a_frases(inicio: float, fin: float, segmentos: list[dict], total: float) -> tuple[float, float]:
    """Mueve el inicio/fin a los bordes de frase más cercanos para no cortar a mitad de palabra."""
    ini = min(segmentos, key=lambda s: abs(s["inicio"] - inicio))["inicio"]
    fin = min(segmentos, key=lambda s: abs(s["fin"] - fin))["fin"]
    if fin - ini < 10:
        fin = min(ini + 30, total)
    fin = min(fin, ini + 75, total)
    return max(ini - 0.15, 0), min(fin + 0.35, total)


def crear_clip(tramo: Path, c: Clip, numero: int, ini: float, segmentos: list[dict],
               ruta_fuente: Path, carpeta: Path) -> Path:
    """Monta el clip vertical 1080x1920 a partir de un tramo que empieza en el segundo `ini` del original."""
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "fuentes").mkdir(exist_ok=True)
    (carpeta / "fuentes" / ruta_fuente.name).write_bytes(ruta_fuente.read_bytes())
    nombre_fuente = ImageFont.truetype(str(ruta_fuente), 10).getname()[0]
    fin = ini + duracion(tramo)
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
    salida = f"clip_{numero}.mp4"
    ejecutar([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(tramo.resolve()), "-i", f"clip_{numero}_capa.png",
        "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", salida,
    ], cwd=carpeta)
    return carpeta / salida
