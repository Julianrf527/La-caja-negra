"""Estado en memoria: un EstadoToken por token. /__reset lo reemplaza por uno nuevo."""

from dataclasses import dataclass, field


@dataclass
class Cuenta:
    titular: str
    saldo: int = 0
    fallos_seguidos: int = 0
    bloqueada: bool = False
    # Nº de E510 seguidos de esta cuenta como origen (v2). Se reinicia al desbloquear con depósito.
    intentos_bloqueo: int = 0


@dataclass
class Operacion:
    tipo: str  # "deposito" | "transfer"
    origen: str | None
    destino: str | None
    monto: int
    anulada: bool = False


@dataclass
class EstadoToken:
    cuentas: dict[str, Cuenta] = field(default_factory=dict)
    operaciones: dict[str, Operacion] = field(default_factory=dict)
    n_cuentas: int = 0
    n_operaciones: int = 0
    detenido: bool = False

    def nueva_cuenta(self, titular: str, prefijo: str, ancho: int) -> str:
        self.n_cuentas += 1
        id_ = f"{prefijo}{self.n_cuentas:0{ancho}d}"
        self.cuentas[id_] = Cuenta(titular)
        return id_

    def nueva_operacion(self, op: Operacion, prefijo: str, ancho: int) -> str:
        self.n_operaciones += 1
        id_ = f"{prefijo}{self.n_operaciones:0{ancho}d}"
        self.operaciones[id_] = op
        return id_


class Almacen:
    def __init__(self):
        self._estados: dict[str, EstadoToken] = {}
        # El contador de X-Req no se reinicia con /__reset (como en el original).
        self._x_req: dict[str, int] = {}

    def estado(self, token: str) -> EstadoToken:
        if token not in self._estados:
            self._estados[token] = EstadoToken()
        return self._estados[token]

    def reset(self, token: str) -> None:
        self._estados[token] = EstadoToken()

    def siguiente_x_req(self, token: str) -> int:
        self._x_req[token] = self._x_req.get(token, 0) + 1
        return self._x_req[token]

    def vaciar(self) -> None:
        self._estados.clear()
        self._x_req.clear()


almacen = Almacen()
