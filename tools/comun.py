"""Utilidades compartidas por las herramientas de tools/.

- Todo request al ORIGINAL pasa por test-original-app/helper/cliente.py (queda en experimentos.jsonl).
- El reemplazo se ejecuta en local con TestClient, sin red. app/ nunca llama al original.
"""

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "test-original-app"))

LOG = RAIZ / "test-original-app" / "experimentos.jsonl"
LINEAS_ANTES_DE_ESTA_TAREA = 2851  # líneas del log al empezar la tarea de afinado
PRESUPUESTO = 3000
SALIDA = RAIZ / "tools" / "salida"
TOKEN_LOCAL = "token-local-herramientas"  # token ficticio solo para el reemplazo en local


def usadas() -> int:
    """Requests hechas al original en esta tarea (líneas nuevas del log)."""
    with LOG.open(encoding="utf-8") as f:
        return sum(1 for _ in f) - LINEAS_ANTES_DE_ESTA_TAREA


def cliente_original(max_requests: int):
    from helper.cliente import Cliente  # noqa: E402  (ruta añadida arriba)

    return Cliente(max_requests=max_requests)


class Local:
    """El reemplazo en local, con su propio estado y su propio reset."""

    def __init__(self):
        os.environ["TOKEN_EQUIPO"] = TOKEN_LOCAL
        os.environ.pop("VERSION_REGLAS", None)
        from fastapi.testclient import TestClient

        import app.captura as captura
        from app.main import app

        captura.registrar = lambda *a, **k: None  # sin ruido en consola
        self.http = TestClient(app)
        self.auth = {"Authorization": f"Bearer {TOKEN_LOCAL}"}

    def reset(self):
        return self.http.post("/__reset", headers=self.auth)

    def peticion(self, metodo: str, ruta: str, cuerpo: str | None = None, con_token: bool = True):
        contenido = cuerpo.encode("utf-8") if cuerpo is not None else None
        r = self.http.request(metodo, ruta, content=contenido, headers=self.auth if con_token else {})
        return r.status_code, _parsear(r.text)

    def msg_crudo(self, cuerpo: str):
        return self.peticion("POST", "/msg", cuerpo)


def _parsear(texto: str):
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def iguales(status_a: int, resp_a, status_b: int, resp_b) -> bool:
    """Reglas del reto: mismo status y mismo cuerpo (JSON: claves en cualquier orden; si no, texto exacto)."""
    return status_a == status_b and resp_a == resp_b


def resumen(status: int, resp) -> str:
    if isinstance(resp, dict) and "error" in resp:
        return f"{status} {resp['error']}"
    return f"{status} {json.dumps(resp, ensure_ascii=False)[:80]}"


def aplanar_anidados() -> int:
    """Sustituye en el log los cuerpos JSON muy anidados (que pydantic no puede releer) por su texto.

    Cliente guarda `request` ya parseado; una lista anidada a más de ~200 niveles hace fallar a
    Bitacora.leer. Se reescribe esa línea con el cuerpo como texto (el contenido real enviado).
    """
    lineas = LOG.read_text(encoding="utf-8").split("\n")
    cambios = 0
    for k, linea in enumerate(lineas):
        if '"request": [[[[' in linea or '"request": {"a": {"a"' in linea:
            i = linea.index('"request": ') + len('"request": ')
            j = linea.index(', "status":')
            original = linea[i:j]
            if original.count("[") > 150 or original.count("{") > 150:
                lineas[k] = linea[:i] + json.dumps(original) + linea[j:]
                cambios += 1
    LOG.write_text("\n".join(lineas), encoding="utf-8", newline="\n")
    return cambios
