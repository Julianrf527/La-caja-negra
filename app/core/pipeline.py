"""Pipeline de validación de POST /msg, en el orden que dicta el perfil (`orden_pipeline`)."""

import json
from dataclasses import dataclass, field
from typing import Any

from app.comandos import Contexto, ejecutar
from app.core import control
from app.core.sugerencia import sugerir
from app.estado.estado import EstadoToken
from app.respuestas.compat import Fallo


@dataclass
class Ctx:
    perfil: dict
    estado: EstadoToken
    crudo: bytes
    datos: Any = None
    m: str = ""
    segmentos: list[str] = field(default_factory=list)
    comando: str = ""  # en mayúsculas
    args: list[str] = field(default_factory=list)
    control: str = ""

    @property
    def def_comando(self) -> dict | None:
        return self.perfil["comandos"].get(self.comando)

    def cuerpo_sin_control(self) -> str:
        """El mensaje sin el último ';control'."""
        return self.perfil["limites"]["separador"].join(self.segmentos[:-1])

    @property
    def valida_control(self) -> bool:
        d = self.def_comando
        return True if d is None else d["valida_control"]


def _profundidad(dato) -> int:
    """Niveles de anidamiento de listas/objetos (un valor simple vale 0; el objeto raíz cuenta 1)."""
    maxima, pila = 0, [(dato, 1)]
    while pila:
        actual, nivel = pila.pop()
        if isinstance(actual, dict):
            hijos = actual.values()
        elif isinstance(actual, list):
            hijos = actual
        else:
            continue
        maxima = max(maxima, nivel)
        pila.extend((h, nivel + 1) for h in hijos)
    return maxima


def _rechazar_constante(nombre: str):
    """El original rechaza NaN, Infinity y -Infinity aunque Python los acepte (confirmado: #4618, #4627)."""
    raise ValueError(f"constante JSON no permitida: {nombre}")


# Cada paso devuelve None si pasa, o un Fallo.
def _e599(c: Ctx):
    return Fallo("E599") if c.estado.detenido else None


def _e101(c: Ctx):
    return Fallo("E101") if len(c.crudo) > c.perfil["limites"]["max_cuerpo_bytes"] else None


def _e100(c: Ctx):
    try:
        c.datos = json.loads(c.crudo.decode("utf-8"), parse_constant=_rechazar_constante)
    except (ValueError, RecursionError):  # UnicodeDecodeError es ValueError
        return Fallo("E100")
    if _profundidad(c.datos) > c.perfil["limites"]["max_profundidad_json"]:
        return Fallo("E100")
    return None


def _e102(c: Ctx):
    if not isinstance(c.datos, dict) or not isinstance(c.datos.get("m"), str):
        return Fallo("E102")
    c.m = c.datos["m"]
    return None


def _e103(c: Ctx):
    return Fallo("E103") if c.perfil["limites"]["separador"] not in c.m else None


def _e104(c: Ctx):
    c.segmentos = c.m.split(c.perfil["limites"]["separador"])
    if any(s == "" for s in c.segmentos):
        return Fallo("E104")
    c.comando = control.mayusculas_ascii(c.segmentos[0])
    c.args = c.segmentos[1:-1]
    c.control = c.segmentos[-1]
    return None


def _e201(c: Ctx):
    if c.valida_control and not control.forma_valida(c.control, c.perfil):
        return Fallo("E201")
    return None


def _e202(c: Ctx):
    if not c.valida_control:
        return None
    cuerpo = c.cuerpo_sin_control()
    return Fallo("E202") if c.control != control.esperado(cuerpo, c.perfil) else None


def _e301(c: Ctx):
    if c.comando in c.perfil["comandos"]:
        return None
    clave = c.perfil["sugerencia"]["clave"]
    candidatos = list(c.perfil["comandos"])
    if c.perfil["sugerencia"].get("desempate") == "alfabetico":
        candidatos.sort()
    s = sugerir(c.comando, candidatos, c.perfil["limites"]["distancia_sugerencia"])
    return Fallo("E301", {clave: s} if s else {})


def _e302(c: Ctx):
    return Fallo("E302") if len(c.args) != c.def_comando["aridad"] else None


PASOS = {
    "E599": _e599, "E101": _e101, "E100": _e100, "E102": _e102, "E103": _e103,
    "E104": _e104, "E201": _e201, "E202": _e202, "E301": _e301, "E302": _e302,
}


def procesar(crudo: bytes, estado: EstadoToken, perfil: dict):
    """Valida y ejecuta el mensaje. Devuelve Exito o Fallo."""
    c = Ctx(perfil, estado, crudo)
    for nombre in perfil["orden_pipeline"]:
        fallo = PASOS[nombre](c)
        if fallo is not None:
            return fallo
    return ejecutar(c.comando, Contexto(perfil, estado, c.args))
