"""Flujo completo del trabajador con un video local; la IA, la transcripción y Storage se simulan."""
import shutil
import subprocess
import uuid

import psycopg
from psycopg.rows import dict_row

from agente.analisis import ResultadoAnalisis
from agente.modelos import Analisis, Clip, Nota, Titular

FRASE = "el gobierno nos mintió sobre las cifras del gas y yo tengo los documentos que lo prueban"


class AlmacenamientoFalso:
    def __init__(self, *a, **k):
        pass

    origen = None
    subidos: list = []

    def descargar(self, ruta, local):
        shutil.copy(self.origen, local)
        return local

    def subir(self, local, ruta):
        AlmacenamientoFalso.subidos.append(ruta)
        return ruta


def test_procesar_video_archivo(db_url, tmp_path, monkeypatch):
    from worker import pipeline

    video = tmp_path / "entrevista.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=40",
                    "-f", "lavfi", "-i", "sine=d=40", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(video)],
                   check=True)
    palabras = [{"inicio": 2 + i * 0.5, "fin": 2.4 + i * 0.5, "p": p} for i, p in enumerate(FRASE.split())]
    segmentos = [{"inicio": 2, "fin": 2 + len(palabras) * 0.5, "texto": FRASE, "palabras": palabras},
                 {"inicio": 15, "fin": 35, "texto": "segunda parte de la entrevista", "palabras": []}]

    titulares = [Titular(etiqueta="EXCLUSIVO", titular=f"TITULAR {n}", palabra_clave="TITULAR",
                         cita_textual="nos mintió sobre las cifras del gas", segundo_captura=0, por_que_funciona="-")
                 for n in range(4)]
    titulares.append(Titular(etiqueta="FALSO", titular="INVENTADO", palabra_clave="INVENTADO",
                             cita_textual="el ministro robó todo el dinero", segundo_captura=0, por_que_funciona="-"))
    analisis = Analisis(invitado="Juan Pérez", resumen="Resumen.", titulares=titulares,
                        clips=[Clip(titulo_gancho="NOS MINTIERON", palabra_clave="MINTIERON", inicio=2, fin=30,
                                    cita_textual="yo tengo los documentos que lo prueban", por_que_funciona="-")],
                        nota=Nota(titulo="T", bajada="B", cuerpo="C", texto_facebook="F"))

    AlmacenamientoFalso.origen = video
    monkeypatch.setattr(pipeline, "Almacenamiento", AlmacenamientoFalso)
    monkeypatch.setattr(pipeline, "transcribir", lambda *a, **k: segmentos)
    monkeypatch.setattr(pipeline, "analizar",
                        lambda *a, **k: ResultadoAnalisis(analisis, 20000, 5000, "claude-opus-5-5"))
    monkeypatch.setenv("CARPETA_TRABAJO", str(tmp_path / "trabajo"))
    from app.config import config
    config.cache_clear()

    video_id = str(uuid.uuid4())
    with psycopg.connect(db_url, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("insert into videos (id, origen, titulo, archivo_ruta) values (%s, 'archivo', 'Prueba', %s)",
                     (video_id, f"videos/{video_id}/original.mp4"))

    consumo = pipeline.procesar_video({"id": 1, "video_id": video_id, "datos": {}})

    assert consumo == {"tokens_entrada": 20000, "tokens_salida": 5000, "costo_usd": 0.18}
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        v = conn.execute("select estado, invitado from videos where id = %s", (video_id,)).fetchone()
        piezas = conn.execute("select tipo, contenido from piezas where video_id = %s order by tipo, orden",
                              (video_id,)).fetchall()
    assert v == {"estado": "listo", "invitado": "Juan Pérez"}
    tipos = [p["tipo"] for p in piezas]
    assert tipos.count("titular") == 4          # el titular con cita inventada se descartó
    assert tipos.count("clip") == 1 and tipos.count("nota") == 1
    assert piezas[0]["contenido"]["segundo_captura"] == 3.0  # corregido al tiempo real de la cita
