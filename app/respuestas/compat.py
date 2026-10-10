"""Capa de compatibilidad: convierte resultados de dominio en status + cuerpo exactos del original.

Rarezas que se replican aquí a propósito: la errata "recieved", las claves inconsistentes
(cuentaId / cuenta_id / operacionId), el espacio final de E301, status asimétricos,
HEAD con 404 sin cuerpo y la sugerencia opcional. Todos los textos y claves vienen del perfil.
"""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Exito:
    tipo: str  # clave en reglas["respuestas"]
    datos: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fallo:
    codigo: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Salida:
    status: int
    cuerpo: bytes
    json: Any | None


def _salida(status: int, objeto: Any) -> Salida:
    texto = json.dumps(objeto, ensure_ascii=False, separators=(",", ":"))
    return Salida(status, texto.encode("utf-8"), objeto)


def error(codigo: str, perfil: dict, extra: dict | None = None) -> Salida:
    e = perfil["errores"][codigo]
    cuerpo = {"error": codigo, "mensaje": e["mensaje"]}
    if extra:
        cuerpo.update(extra)
    return _salida(e["status"], cuerpo)


def ruta_desconocida(metodo: str, perfil: dict) -> Salida:
    if metodo == "HEAD" and perfil["head_cuerpo_vacio"]:
        return Salida(perfil["errores"]["E404"]["status"], b"", None)
    return error("E404", perfil)


def estatica(nombre: str, perfil: dict) -> Salida:
    r = perfil["respuestas"][nombre]
    return _salida(r["status"], r["cuerpo"])


def render(resultado: "Exito | Fallo", perfil: dict) -> Salida:
    if isinstance(resultado, Fallo):
        return error(resultado.codigo, perfil, resultado.extra)
    r = perfil["respuestas"][resultado.tipo]
    d = resultado.datos
    t = resultado.tipo
    if t in ("pong", "ya_anulada"):
        cuerpo = dict(r["cuerpo"])
    elif t == "cuenta_creada":
        cuerpo = {r["clave_id"]: d["id"]}
    elif t == "saldo":
        cuerpo = {r["clave_id"]: d["id"], r["clave_saldo"]: d["saldo"]}
    elif t == "operacion_recibida":
        cuerpo = {r["clave_estado"]: r["texto_estado"], r["clave_id"]: d["id"]}
    elif t == "anulada":
        cuerpo = {**r["cuerpo"], r["clave_id"]: d["id"]}
    elif t == "notas":
        cuerpo = {r["clave"]: r["contenido"]}
    else:
        raise KeyError(f"respuesta desconocida: {t}")
    return _salida(r["status"], cuerpo)
