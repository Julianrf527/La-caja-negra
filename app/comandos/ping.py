from app.comandos.base import Contexto
from app.respuestas.compat import Exito


def handler(c: Contexto):
    return Exito("pong")
