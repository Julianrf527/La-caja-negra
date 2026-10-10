from app.comandos.base import Contexto, ids, monto_valido
from app.estado.estado import Operacion
from app.respuestas.compat import Exito, Fallo


def _E303(c):
    return not monto_valido(c, c.args[1])


def _E401(c):
    return c.args[0] not in c.estado.cuentas


_CHECKS = {"E303": _E303, "E401": _E401}


def handler(c: Contexto):
    for codigo in c.perfil["comandos"]["DEPOSITO"]["validaciones"]:
        if _CHECKS[codigo](c):
            return Fallo(codigo)
    cuenta = c.estado.cuentas[c.args[0]]
    monto = int(c.args[1])
    cuenta.saldo += monto
    # Todo depósito a la cuenta la desbloquea y reinicia su contador de fallos (confirmado: #3716-#3723).
    cuenta.bloqueada = False
    cuenta.fallos_seguidos = 0
    cuenta.intentos_bloqueo = 0  # v2: el próximo ciclo de bloqueo cuenta intentos desde 1
    _, prefijo_op, ancho = ids(c)
    op = c.estado.nueva_operacion(Operacion("deposito", None, c.args[0], monto), prefijo_op, ancho)
    return Exito("operacion_recibida", {"id": op})
