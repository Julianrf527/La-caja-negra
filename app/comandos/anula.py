from app.comandos.base import Contexto
from app.respuestas.compat import Exito, Fallo


def handler(c: Contexto):
    op = c.estado.operaciones.get(c.args[0])
    if op is None:
        return Fallo("E402")
    if op.anulada:
        return Exito("ya_anulada")
    op.anulada = True
    cuentas = c.estado.cuentas
    if op.tipo == "deposito":
        cuentas[op.destino].saldo -= op.monto
    else:
        cuentas[op.origen].saldo += op.monto
        cuentas[op.destino].saldo -= op.monto
    return Exito("anulada", {"id": c.args[0]})
