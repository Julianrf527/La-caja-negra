from app.comandos.base import Contexto
from app.respuestas.compat import Fallo


def handler(c: Contexto):
    if c.args[0] != c.perfil["limites"]["confirmacion_halt"]:
        return Fallo("E520")
    c.estado.detenido = True
    return Fallo("E599")
