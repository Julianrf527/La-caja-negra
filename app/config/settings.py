"""Variables de entorno del servicio. Se leen en cada llamada (no se cachean)."""

import os

VARIABLE_TOKEN = "TOKEN_EQUIPO"
VARIABLE_VERSION = "VERSION_REGLAS"
VERSION_POR_DEFECTO = "v1"


def token_equipo(variable: str = VARIABLE_TOKEN) -> str:
    """Token válido del equipo ('' si no está definido: entonces nadie se autentica)."""
    return os.environ.get(variable, "")


def version_reglas() -> str:
    return os.environ.get(VARIABLE_VERSION) or VERSION_POR_DEFECTO
