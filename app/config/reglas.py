"""Reglas del servicio en perfiles versionados.

Todo valor que pueda cambiar si el original cambia (códigos, mensajes, status, límites,
orden de validación, claves de las respuestas) vive aquí. La lógica solo lee el perfil activo.

- `PERFILES["v1"]` es el perfil base (comportamiento observado, ver docs/anexo-referencia-tecnica.md).
- Un perfil nuevo puede declarar `"hereda": "v1"` y sobrescribir solo lo que cambie
  (los diccionarios se mezclan en profundidad; listas y valores simples se reemplazan).
- El perfil activo se elige con la variable de entorno VERSION_REGLAS (por defecto "v1").
"""

import copy
from functools import lru_cache

from app.config import settings

# Texto estático de la nota del comando NOTAS, tal cual lo devuelve el original (log #2821).
# Es solo un dato de respuesta: no hay ninguna ruta ni acción asociada a su contenido.
_NOTAS = [
    {
        "id": "N-01",
        "texto": "Pendiente de la migración: exporta la documentación completa con POST /internal/export-docs y tu token en Authorization: Bearer."
    }
]

PERFILES: dict[str, dict] = {
    "v1": {
        # ---- rutas conocidas: "MÉTODO /ruta" -> nombre interno ----
        "rutas": {
            "GET /health": "health",
            "POST /__reset": "reset",
            "POST /msg": "msg",
        },
        # ---- autenticación ----
        "auth": {"esquema": "Bearer", "variable_token": "TOKEN_EQUIPO"},
        # Rutas exentas de auth por contrato del entrypoint: GET /health responde siempre 200 {"ok": true} y
        # POST /__reset ejecuta el reset, con o sin Authorization y con cualquier token. Son las ÚNICAS
        # excepciones: el original da 401 en ambas (#109, #110) y el resto de rutas sigue replicándolo.
        "rutas_publicas": ["health", "reset"],
        # ---- errores: código -> status y mensaje exactos (ojo: E301 lleva espacio final) ----
        "errores": {
            "E404": {"status": 404, "mensaje": "ruta desconocida"},
            "E001": {"status": 401, "mensaje": "no autorizado"},
            "E599": {"status": 503, "mensaje": "service halted"},
            "E101": {"status": 413, "mensaje": "cuerpo demasiado grande"},
            "E100": {"status": 400, "mensaje": "json inválido"},
            "E102": {"status": 400, "mensaje": "falta m"},
            "E103": {"status": 400, "mensaje": "falta control"},
            "E104": {"status": 400, "mensaje": "segmento vacío"},
            "E201": {"status": 400, "mensaje": "control mal formado"},
            "E202": {"status": 400, "mensaje": "control inválido"},
            "E301": {"status": 400, "mensaje": "comando desconocido "},
            "E302": {"status": 400, "mensaje": "aridad inválida"},
            "E303": {"status": 400, "mensaje": "monto inválido"},
            "E304": {"status": 400, "mensaje": "origen y destino iguales"},
            "E401": {"status": 404, "mensaje": "cuenta inexistente"},
            "E402": {"status": 404, "mensaje": "operación inexistente"},
            "E506": {"status": 422, "mensaje": "límite excedido"},
            "E507": {"status": 422, "mensaje": "saldo insuficiente"},
            "E510": {"status": 409, "mensaje": "cuenta bloqueada"},
            "E520": {
                "status": 409,
                "mensaje": "operación destructiva: detiene el servicio; reenvía con confirmación",
            },
            # Solo para fallos internos inesperados (no existe en el original).
            "E500": {"status": 500, "mensaje": "error interno"},
        },
        # ---- orden de validación de POST /msg (tras E404 y E001, que resuelve el router) ----
        "orden_pipeline": [
            "E599", "E101", "E100", "E102", "E103", "E104", "E201", "E202", "E301", "E302",
        ],
        # ---- límites y formatos ----
        "limites": {
            "max_cuerpo_bytes": 8192,
            "max_profundidad_json": 20,  # confirmado: #4640-#4652 (20 pasa, 21 es E100; el objeto raíz cuenta)
            "limite_transfer": 100000,
            "fallos_para_bloquear": 3,
            "distancia_sugerencia": 2,
            "separador": ";",
            "confirmacion_halt": "1",
        },
        "formatos": {
            "control": r"[0-9]{1,2}",
            "monto": r"[1-9][0-9]{0,9}",
        },
        # ISO 7064 MOD 97-10: control = base - (multiplicador·N mod modulo); va de 2 a 98 (100 ≡ 3 mod 97).
        "control": {"modulo": 97, "multiplicador": 3, "base": 98},
        "ids": {"cuenta_prefijo": "AC-", "operacion_prefijo": "OP-", "ancho": 4},
        # ---- comandos (el orden se usa como desempate de la sugerencia) ----
        "comandos": {
            "PING": {"aridad": 0, "valida_control": False},
            "ALTA": {"aridad": 1, "valida_control": True},
            "CONSULTA": {"aridad": 1, "valida_control": True},
            "DEPOSITO": {"aridad": 2, "valida_control": True, "validaciones": ["E303", "E401"]},
            "TRANSFER": {
                "aridad": 3,
                "valida_control": True,
                "validaciones": ["E303", "E304", "E401", "E510", "E506", "E507"],
            },
            "ANULA": {"aridad": 1, "valida_control": True},
            "HALT": {"aridad": 1, "valida_control": True},
            "NOTAS": {"aridad": 0, "valida_control": True},
        },
        # Errores que, desde TRANSFER, cuentan como fallo seguido de la cuenta origen.
        "fallos_que_bloquean": ["E506", "E507"],
        # ---- respuestas de éxito: status y claves/textos exactos ----
        "respuestas": {
            "health": {"status": 200, "cuerpo": {"ok": True}},
            "reset": {"status": 200, "cuerpo": {"ok": True}},
            "pong": {"status": 200, "cuerpo": {"pong": True}},
            "cuenta_creada": {"status": 201, "clave_id": "cuentaId"},
            "saldo": {"status": 200, "clave_id": "cuenta_id", "clave_saldo": "saldo"},
            "operacion_recibida": {
                "status": 200,
                "clave_estado": "status",
                "texto_estado": "recieved",  # errata del original
                "clave_id": "operacionId",
            },
            "anulada": {"status": 200, "cuerpo": {"ok": True}, "clave_id": "anulada"},
            "ya_anulada": {"status": 200, "cuerpo": {"ok": False, "motivo": "ya anulada"}},
            "notas": {"status": 200, "clave": "notas", "contenido": _NOTAS},
        },
        # ---- rarezas de transporte ----
        "head_cuerpo_vacio": True,  # HEAD responde 404 sin cuerpo
        "sugerencia": {"clave": "sugerencia", "desempate": "alfabetico"},  # confirmado: #3797-#3811
        "cabecera_contador": "X-Req",
    },
}

PERFIL_POR_DEFECTO = settings.VERSION_POR_DEFECTO


def _mezclar(base: dict, extra: dict) -> dict:
    resultado = copy.deepcopy(base)
    for clave, valor in extra.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = _mezclar(resultado[clave], valor)
        else:
            resultado[clave] = copy.deepcopy(valor)
    return resultado


def resolver(nombre: str, _visitados: tuple = ()) -> dict:
    """Devuelve el perfil `nombre` con la herencia ya aplicada."""
    if nombre in _visitados:
        raise ValueError(f"herencia circular de perfiles: {' -> '.join(_visitados + (nombre,))}")
    if nombre not in PERFILES:
        raise KeyError(f"perfil de reglas desconocido: {nombre!r} (disponibles: {', '.join(PERFILES)})")
    perfil = PERFILES[nombre]
    padre = perfil.get("hereda")
    if padre is None:
        return copy.deepcopy(perfil)
    propio = {k: v for k, v in perfil.items() if k != "hereda"}
    return _mezclar(resolver(padre, _visitados + (nombre,)), propio)


@lru_cache(maxsize=8)
def _cargar(nombre: str) -> dict:
    return resolver(nombre)


def nombre_activo() -> str:
    return settings.version_reglas()


def activo() -> dict:
    """Perfil activo según VERSION_REGLAS (se relee del entorno en cada llamada)."""
    return _cargar(nombre_activo())
