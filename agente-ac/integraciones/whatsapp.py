"""WhatsApp Cloud API (semana 3): aviso al gerente con botones y lectura de sus respuestas.

Plantillas aprobadas en Meta: `propuestas_listas` y `contenido_publicado` (categoría Utilidad).
Endpoint: POST https://graph.facebook.com/{version}/{phone_number_id}/messages
"""


def enviar_propuestas(video_id: str, destinatario: str) -> str:
    """Envía la plantilla `propuestas_listas` y, dentro de la ventana de 24 h, el resumen con
    botones Aprobar / Cambios / Rechazar. Devuelve el id del mensaje de Meta."""
    raise NotImplementedError("Semana 3")


def procesar_respuesta(evento: dict) -> None:
    """Interpreta la respuesta del webhook: registra la aprobación, encola la publicación o,
    si pidió cambios, encola `procesar_video` con su comentario como instrucción."""
    raise NotImplementedError("Semana 3")
