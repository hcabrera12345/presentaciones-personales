"""Esquemas de lo que produce el agente. Claude responde con estas estructuras validadas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Titular(BaseModel):
    etiqueta: str = Field(description="Cintillo rojo corto en mayúsculas: 'ÚLTIMA HORA', 'EXCLUSIVO', 'POLÉMICA', 'REVELA', 'ALERTA'…")
    titular: str = Field(description="Titular picante, máximo 70 caracteres, en mayúsculas")
    palabra_clave: str = Field(description="1 a 3 palabras EXACTAS del titular que se resaltan en amarillo")
    cita_textual: str = Field(description="Frase copiada LITERALMENTE de la transcripción que respalda el titular")
    segundo_captura: float = Field(description="Segundo del video donde el entrevistado dice la cita")
    por_que_funciona: str = Field(description="Una línea: por qué este titular engancha")


class Clip(BaseModel):
    titulo_gancho: str = Field(description="Gancho del clip en mayúsculas, máximo 55 caracteres")
    palabra_clave: str = Field(description="1 a 2 palabras EXACTAS del gancho que se resaltan en amarillo")
    inicio: float = Field(description="Segundo de inicio (al comienzo de una frase)")
    fin: float = Field(description="Segundo de fin (al terminar una idea); duración entre 20 y 60 s")
    cita_textual: str = Field(description="Frase central del clip, copiada LITERALMENTE de la transcripción")
    por_que_funciona: str = Field(description="Una línea: por qué este momento funciona como Reel")


class Nota(BaseModel):
    titulo: str = Field(description="Título de la nota periodística")
    bajada: str = Field(description="Bajada o copete de 1 a 2 frases")
    cuerpo: str = Field(description="Nota de 300 a 450 palabras en estilo periodístico, con citas textuales entre comillas")
    texto_facebook: str = Field(description="Texto para acompañar la publicación en Facebook, máximo 400 caracteres")


class Analisis(BaseModel):
    invitado: str = Field(description="Nombre y cargo del entrevistado si se menciona; si no, 'Invitado'")
    resumen: str = Field(description="Resumen de la entrevista en 2 frases")
    titulares: list[Titular] = Field(description="Exactamente 5 titulares, del más fuerte al menos fuerte")
    clips: list[Clip] = Field(description="Exactamente 3 clips que no se solapen")
    nota: Nota
