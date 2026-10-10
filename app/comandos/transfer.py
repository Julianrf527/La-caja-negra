from app.comandos.base import Contexto, ids, monto_valido
from app.estado.estado import Operacion
from app.respuestas.compat import Exito, Fallo


def _E303(c):
    return not monto_valido(c, c.args[2])


def _E304(c):
    return c.args[0] == c.args[1]


def _E401(c):
    return c.args[0] not in c.estado.cuentas or c.args[1] not in c.estado.cuentas


def _E510(c):
    return c.estado.cuentas[c.args[0]].bloqueada


def _E506(c):
    origen, destino = c.estado.cuentas[c.args[0]], c.estado.cuentas[c.args[1]]
    if origen.titular == destino.titular:  # mismo titular: sin límite
        return False
    return int(c.args[2]) > c.perfil["limites"]["limite_transfer"]


def _E507(c):
    return c.estado.cuentas[c.args[0]].saldo < int(c.args[2])


_CHECKS = {"E303": _E303, "E304": _E304, "E401": _E401, "E510": _E510, "E506": _E506, "E507": _E507}


def handler(c: Contexto):
    for codigo in c.perfil["comandos"]["TRANSFER"]["validaciones"]:
        if _CHECKS[codigo](c):
            if codigo in c.perfil["fallos_que_bloquean"]:
                origen = c.estado.cuentas[c.args[0]]
                origen.fallos_seguidos += 1
                if origen.fallos_seguidos >= c.perfil["limites"]["fallos_para_bloquear"]:
                    origen.bloqueada = True
            return Fallo(codigo)
    origen, destino = c.estado.cuentas[c.args[0]], c.estado.cuentas[c.args[1]]
    monto = int(c.args[2])
    origen.saldo -= monto
    destino.saldo += monto
    origen.fallos_seguidos = 0
    _, prefijo_op, ancho = ids(c)
    op = c.estado.nueva_operacion(Operacion("transfer", c.args[0], c.args[1], monto), prefijo_op, ancho)
    return Exito("operacion_recibida", {"id": op})
