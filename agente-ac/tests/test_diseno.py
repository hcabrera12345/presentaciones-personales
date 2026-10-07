import subprocess

from PIL import Image

from agente import diseno
from agente.modelos import Clip, Titular


def _video_prueba(ruta, segundos=6):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1280x720:d={segundos}",
                    "-f", "lavfi", "-i", f"sine=d={segundos}", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(ruta)], check=True)
    return ruta


def test_miniatura_1280x720(tmp_path):
    t = Titular(etiqueta="EXCLUSIVO", titular="EXGERENTE REVELA: NOS MINTIERON CON EL GAS", palabra_clave="NOS MINTIERON",
                cita_textual="nos mintieron", segundo_captura=1, por_que_funciona="-")
    destino = tmp_path / "t.jpg"
    diseno.crear_miniatura(Image.new("RGB", (1920, 1080), (40, 60, 90)), t, diseno.buscar_fuente(None), destino)
    assert Image.open(destino).size == (1280, 720)


def test_mejor_fotograma_y_clip_vertical(tmp_path):
    tramo = _video_prueba(tmp_path / "tramo.mp4")
    assert diseno.mejor_fotograma(tramo, tmp_path).size == (1280, 720)

    palabras = [{"inicio": 100 + i * 0.5, "fin": 100.4 + i * 0.5, "p": p}
                for i, p in enumerate("esto es una prueba del clip vertical".split())]
    segmentos = [{"inicio": 100, "fin": 104, "texto": "esto es una prueba del clip vertical", "palabras": palabras}]
    c = Clip(titulo_gancho="LO QUE NADIE TE CUENTA", palabra_clave="NADIE", inicio=100, fin=106,
             cita_textual="esto es una prueba", por_que_funciona="-")
    salida = diseno.crear_clip(tramo, c, 1, 100.0, segmentos, diseno.buscar_fuente(None), tmp_path / "clips")
    dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height", "-of", "csv=p=0", str(salida)],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert dims == "1080,1920"


def test_ajustar_a_frases_respeta_bordes():
    segmentos = [{"inicio": 10, "fin": 20}, {"inicio": 21, "fin": 45}, {"inicio": 46, "fin": 60}]
    assert diseno.ajustar_a_frases(20.5, 44, segmentos, 600) == (20.85, 45.35)
