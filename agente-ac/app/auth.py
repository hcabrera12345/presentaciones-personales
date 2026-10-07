"""Autenticación: el navegador inicia sesión con Google vía Supabase Auth y envía el token
de acceso en la cookie `sb_token`; aquí se valida la firma y se exige un perfil activo."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request

from app.config import config
from app.db import conexion


@dataclass
class Usuario:
    id: str | None
    email: str
    nombre: str
    rol: str

    def puede_aprobar(self) -> bool:
        return self.rol in ("admin", "gerente")


class NoAutenticado(Exception):
    """Sin sesión válida: las páginas redirigen a /login."""


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{config().supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _validar_token(token: str) -> dict:
    cfg = config()
    opciones = {"audience": "authenticated"}
    if cfg.supabase_jwt_secret:  # proyectos con la firma HS256 heredada
        return jwt.decode(token, cfg.supabase_jwt_secret, algorithms=["HS256"], **opciones)
    clave = _jwks().get_signing_key_from_jwt(token).key
    return jwt.decode(token, clave, algorithms=["ES256", "RS256"], **opciones)


def usuario_actual(request: Request) -> Usuario:
    cfg = config()
    if cfg.auth_desactivada and not cfg.es_produccion:
        return Usuario(id=None, email="dev@local", nombre="Desarrollo", rol="admin")

    token = request.cookies.get("sb_token") or request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token:
        raise NoAutenticado()
    try:
        datos = _validar_token(token)
    except jwt.PyJWTError:
        raise NoAutenticado()

    with conexion() as conn:
        perfil = conn.execute("select * from perfiles where id = %s", (datos["sub"],)).fetchone()
    if not perfil or not perfil["activo"]:
        raise HTTPException(403, "Tu cuenta está pendiente de activación por un administrador.")
    return Usuario(id=str(perfil["id"]), email=perfil["email"], nombre=perfil["nombre"] or perfil["email"],
                   rol=perfil["rol"])
