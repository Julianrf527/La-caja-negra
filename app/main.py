"""Reemplazo de «La caja negra». Una ruta comodín recibe todo; el router y la auth se resuelven a mano.

Orden: E404 (ruta) → E001 (auth) → /health y /__reset salen directo → /msg entra al pipeline.
Sin red saliente: este módulo no importa ningún cliente HTTP.
"""

import hmac

from fastapi import FastAPI, Request, Response

from app import captura
from app.config import reglas, settings
from app.core import pipeline
from app.estado.estado import almacen
from app.respuestas import compat
from app.respuestas.compat import Salida

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

METODOS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"]


async def _leer_cuerpo(request: Request, tope: int) -> bytes:
    """Lee el cuerpo guardando solo `tope + 1` bytes (basta para decidir E101).

    El resto se consume y se descarta: si no se lee, el servidor deja de leer el socket y un
    cliente que aún está subiendo un cuerpo grande se queda esperando la respuesta.
    """
    guardado = bytearray()
    async for trozo in request.stream():
        if len(guardado) <= tope:
            guardado += trozo[: tope + 1 - len(guardado)]
    return bytes(guardado)


def _token_de(request: Request, perfil: dict) -> str | None:
    """Devuelve el token válido presentado, o None si falta o no coincide."""
    esperado = settings.token_equipo(perfil["auth"]["variable_token"])
    cabecera = request.headers.get("authorization")
    if not esperado or cabecera is None:
        return None
    candidato = f'{perfil["auth"]["esquema"]} {esperado}'
    if hmac.compare_digest(cabecera.encode("utf-8"), candidato.encode("utf-8")):
        return esperado
    return None


def _responder(salida: Salida, extra: dict | None = None) -> Response:
    return Response(
        content=salida.cuerpo,
        status_code=salida.status,
        media_type="application/json" if salida.cuerpo else None,
        headers=extra,
    )


@app.api_route("/{path:path}", methods=METODOS, include_in_schema=False)
async def comodin(request: Request, path: str) -> Response:
    perfil = reglas.activo()
    metodo, ruta = request.method, request.url.path
    cuerpo = b""
    token_valido = False
    salida: Salida
    headers: dict | None = None
    try:
        cuerpo = await _leer_cuerpo(request, perfil["limites"]["max_cuerpo_bytes"])
        destino = perfil["rutas"].get(f"{metodo} {ruta}")
        if destino is None:
            salida = compat.ruta_desconocida(metodo, perfil)
        else:
            token = _token_de(request, perfil)
            token_valido = token is not None
            if token is None:
                salida = compat.error("E001", perfil)
            elif destino == "health":
                salida = compat.estatica("health", perfil)
            elif destino == "reset":
                almacen.reset(token)
                salida = compat.estatica("reset", perfil)
            else:  # msg
                resultado = pipeline.procesar(cuerpo, almacen.estado(token), perfil)
                salida = compat.render(resultado, perfil)
                headers = {perfil["cabecera_contador"]: str(almacen.siguiente_x_req(token))}
    except Exception:  # un fallo interno nunca debe tumbar el proceso
        salida = compat.error("E500", perfil)
    respuesta = _responder(salida, headers)
    captura.registrar(metodo, ruta, cuerpo, token_valido, salida.status, salida.cuerpo)
    return respuesta
