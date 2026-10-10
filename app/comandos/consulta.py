from app.comandos.base import Contexto
from app.respuestas.compat import Exito, Fallo


def handler(c: Contexto):
    cuenta = c.estado.cuentas.get(c.args[0])
    if cuenta is None:
        return Fallo("E401")
    return Exito("saldo", {"id": c.args[0], "saldo": cuenta.saldo})
