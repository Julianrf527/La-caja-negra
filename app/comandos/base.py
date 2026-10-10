"""Contexto y utilidades compartidas por los handlers de comandos."""

import re

from app.estado.estado import EstadoToken


class Contexto:
    """Lo que ve un handler: perfil, estado del token y argumentos (aridad ya validada)."""

    def __init__(self, perfil: dict, estado: EstadoToken, args: list[str]):
        self.perfil = perfil
        self.estado = estado
        self.args = args


def ids(c: Contexto):
    i = c.perfil["ids"]
    return i["cuenta_prefijo"], i["operacion_prefijo"], i["ancho"]


def monto_valido(c: Contexto, texto: str) -> bool:
    return re.fullmatch(c.perfil["formatos"]["monto"], texto) is not None
