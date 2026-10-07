from agente.verificacion import normalizar, ubicar_cita

SEGMENTOS = [
    {"inicio": 10.0, "fin": 14.0, "texto": "El gobierno nos mintió sobre las cifras del gas.",
     "palabras": [{"inicio": 10.0 + i * 0.4, "fin": 10.3 + i * 0.4, "p": p}
                  for i, p in enumerate("El gobierno nos mintió sobre las cifras del gas.".split())]},
    {"inicio": 15.0, "fin": 18.0, "texto": "Yo tengo los documentos que lo prueban.", "palabras": []},
]


def test_normalizar_quita_tildes_y_puntuacion():
    assert normalizar("¡Nos MINTIÓ, sobre el gas!") == "nos mintio sobre el gas"


def test_cita_exacta_devuelve_el_segundo_real():
    similitud, segundo = ubicar_cita("nos mintió sobre las cifras", SEGMENTOS)
    assert similitud == 1.0
    assert segundo == 10.8  # tercera palabra


def test_cita_con_diferencia_minima_se_acepta():
    assert ubicar_cita("El gobierno nos mintio sobre la cifra del gas", SEGMENTOS)


def test_cita_inventada_se_rechaza():
    assert ubicar_cita("el ministro robó todo el dinero del gas", SEGMENTOS) is None


def test_frase_sin_marcas_por_palabra_usa_inicio_de_frase():
    assert ubicar_cita("tengo los documentos que lo prueban", SEGMENTOS)[1] == 15.0
