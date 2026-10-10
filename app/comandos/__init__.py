"""Registro comando → handler. Cada comando vive en su propio archivo."""

from app.comandos.base import Contexto
from app.comandos import alta, anula, consulta, deposito, halt, notas, ping, transfer

HANDLERS = {
    "PING": ping.handler,
    "ALTA": alta.handler,
    "CONSULTA": consulta.handler,
    "DEPOSITO": deposito.handler,
    "TRANSFER": transfer.handler,
    "ANULA": anula.handler,
    "HALT": halt.handler,
    "NOTAS": notas.handler,
}


def ejecutar(comando: str, c: Contexto):
    return HANDLERS[comando](c)
