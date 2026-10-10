from app.comandos.base import Contexto, ids
from app.respuestas.compat import Exito


def handler(c: Contexto):
    prefijo, _, ancho = ids(c)
    return Exito("cuenta_creada", {"id": c.estado.nueva_cuenta(c.args[0], prefijo, ancho)})
