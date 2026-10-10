from app.comandos.base import Contexto
from app.respuestas.compat import Exito


def handler(c: Contexto):
    # Devuelve el texto estático del perfil (reglas["respuestas"]["notas"]); no hace nada más.
    return Exito("notas")
