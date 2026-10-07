"""Publicación en la Página de Facebook del canal (semana 3), con el token del usuario del sistema.

Videos y Reels: POST /{page_id}/videos (o el flujo de Reels de la Graph API)
Fotos:          POST /{page_id}/photos
"""


def publicar_pieza(pieza_id: str, programar_para: str | None = None) -> str:
    """Publica una pieza aprobada y devuelve el id de la publicación en Facebook."""
    raise NotImplementedError("Semana 3")
