"""Análisis de la entrevista con Claude: titulares, clips y nota, con el estilo del canal."""
from __future__ import annotations

from dataclasses import dataclass

import anthropic

from agente.modelos import Analisis

SISTEMA_BASE = """Eres el editor digital del canal de noticias y análisis "Asuntos Centrales" (Bolivia).
Tu trabajo: convertir entrevistas, streamings y documentos en titulares, clips y notas que la gente
quiera abrir y compartir en Facebook.

Estilo del canal:
- Titulares de noticia de última hora: directos, en mayúsculas, con tensión, conflicto o revelación.
- Verbos fuertes (REVELA, ADVIERTE, ROMPE EL SILENCIO, ARREMETE, CONFIESA, DENUNCIA).
- Nombra a la persona o institución cuando eso le dé fuerza al titular.
- Cifras y datos concretos siempre que existan en el material.

Regla innegociable — picante pero verdadero:
- Cada titular y cada clip debe estar respaldado por algo que el entrevistado DIJO LITERALMENTE.
- El campo cita_textual se copia palabra por palabra de la transcripción: un sistema automático
  lo verifica y descarta cualquier propuesta cuya cita no aparezca.
- No inventes hechos, no pongas en boca del invitado lo que no dijo, no exageres cifras.

Para los clips:
- Momentos autosuficientes (se entienden sin contexto), con una idea fuerte o una frase memorable.
- Empiezan al inicio de una frase y terminan cuando la idea se cierra; entre 20 y 60 segundos.
- Los 3 clips son de momentos distintos.
"""


@dataclass
class ResultadoAnalisis:
    analisis: Analisis
    tokens_entrada: int
    tokens_salida: int
    modelo: str


def analizar(segmentos: list[dict], titulo: str, estilo_extra: str, modelo: str,
             instruccion: str = "") -> ResultadoAnalisis:
    """Llama a Claude con la transcripción. `estilo_extra` viene de la tabla estilo_canal (editable)."""
    transcripcion = "\n".join(f"[{s['inicio']:.1f}s] {s['texto']}" for s in segmentos)
    sistema = SISTEMA_BASE + (f"\nIndicaciones del canal:\n{estilo_extra}\n" if estilo_extra else "")
    pedido = "Propón 5 titulares con su momento para la captura, 3 clips cortos y una nota periodística."
    if instruccion:
        pedido += f"\n\nIndicación adicional del equipo: {instruccion}"

    cliente = anthropic.Anthropic()
    respuesta = cliente.beta.messages.parse(
        model=modelo,
        max_tokens=16000,
        system=sistema,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        # Si el modelo principal declina, el servidor reintenta con otro modelo adecuado
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": f"Título del material: {titulo}\n\n<transcripcion>\n{transcripcion}\n</transcripcion>\n\n{pedido}",
        }],
        output_format=Analisis,
    )
    if respuesta.stop_reason == "refusal":
        raise RuntimeError("Claude declinó analizar este contenido")
    if respuesta.parsed_output is None:
        raise RuntimeError(f"Respuesta sin estructura válida (stop_reason={respuesta.stop_reason})")
    return ResultadoAnalisis(
        analisis=respuesta.parsed_output,
        tokens_entrada=respuesta.usage.input_tokens,
        tokens_salida=respuesta.usage.output_tokens,
        modelo=respuesta.model,
    )
