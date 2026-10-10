"""Registro de lo que recibe el servicio: una línea JSON por request en stdout con prefijo CAPTURA.

Nunca escribe el header Authorization ni el token. Cualquier fallo se ignora.
El cuerpo y la respuesta se recortan a MAX_TEXTO caracteres (campo `truncado`) para que una línea
nunca sea enorme: un stdout lento o lleno no debe poder frenar al servicio.
"""

import json
import sys
from datetime import datetime, timezone

MAX_TEXTO = 4096


def _texto(datos: bytes) -> tuple[str, bool]:
    t = datos.decode("utf-8", errors="replace")
    return (t[:MAX_TEXTO], True) if len(t) > MAX_TEXTO else (t, False)


def registrar(metodo: str, ruta: str, cuerpo: bytes, token_valido: bool, status: int, respuesta: bytes) -> None:
    try:
        cuerpo_t, cortado_c = _texto(cuerpo)
        resp_t, cortado_r = _texto(respuesta)
        linea = json.dumps(
            {
                "hora": datetime.now(timezone.utc).isoformat(),
                "metodo": metodo,
                "ruta": ruta[:MAX_TEXTO],
                "cuerpo": cuerpo_t,
                "token_valido": token_valido,
                "status": status,
                "respuesta": resp_t,
                "truncado": cortado_c or cortado_r,
            },
            ensure_ascii=True,  # seguro con cualquier codificación de stdout
        )
        sys.stdout.write("CAPTURA " + linea + "\n")
        sys.stdout.flush()
    except Exception:
        pass
