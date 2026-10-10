"""Pruebas de humo por HTTP real contra un servidor ya levantado (no es un test de pytest).

    TOKEN_EQUIPO=<token> uvicorn app.main:app --port 8000      # en otra terminal
    TOKEN_EQUIPO=<token> python tests/humo_local.py [http://127.0.0.1:8000]

El token se lee de la variable de entorno TOKEN_EQUIPO; no está escrito en ningún archivo.
Sale con código 1 si algo falla.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TOKEN = os.environ.get("TOKEN_EQUIPO", "")
EJEMPLOS = Path(__file__).resolve().parents[1] / "test-original-app/pruebas/ejemplos.jsonl"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

resultados: list[tuple[str, bool, str]] = []
lentas: list[tuple[str, float]] = []


def comprobar(nombre: str, ok: bool, detalle: str = "") -> None:
    resultados.append((nombre, ok, detalle))


def pedir(cliente: httpx.Client, nombre: str, metodo: str, ruta: str, **kw) -> httpx.Response:
    t = time.perf_counter()
    r = cliente.request(metodo, ruta, **kw)
    dt = time.perf_counter() - t
    if dt >= 1:
        lentas.append((nombre, dt))
    return r


def main() -> int:
    if not TOKEN:
        print("Falta la variable de entorno TOKEN_EQUIPO")
        return 2
    e401 = {"error": "E001", "mensaje": "no autorizado"}
    e404 = {"error": "E404", "mensaje": "ruta desconocida"}
    with httpx.Client(base_url=BASE, timeout=5) as c:
        r = pedir(c, "health con token", "GET", "/health", headers=AUTH)
        comprobar("GET /health con token → 200", r.status_code == 200 and r.json() == {"ok": True}, f"{r.status_code} {r.text}")
        r = pedir(c, "health sin token", "GET", "/health")
        comprobar("GET /health sin token → 401 E001", (r.status_code, r.json()) == (401, e401), f"{r.status_code} {r.text}")
        r = pedir(c, "reset", "POST", "/__reset", headers=AUTH)
        comprobar("POST /__reset → 200", r.status_code == 200 and r.json() == {"ok": True}, f"{r.status_code} {r.text}")

        # 20 ejemplos, en orden, tras un reset
        pedir(c, "reset ejemplos", "POST", "/__reset", headers=AUTH)
        casos = [json.loads(l) for l in EJEMPLOS.read_text(encoding="utf-8").splitlines() if l.strip()]
        iguales = 0
        for caso in casos:
            r = pedir(c, f"ejemplo {caso['n']}", "POST", "/msg", headers=AUTH, content=json.dumps(caso["request"]))
            if (r.status_code, r.json()) == (caso["status"], caso["response"]):
                iguales += 1
            else:
                comprobar(f"ejemplo {caso['n']}", False, f"esperado {caso['status']} {caso['response']} / obtenido {r.status_code} {r.text}")
        comprobar(f"ejemplos.jsonl: {iguales}/{len(casos)} iguales", iguales == len(casos) == 20)

        for ruta in ("/docs", "/openapi.json", "/redoc", "/ruta-inventada"):
            r = pedir(c, ruta, "GET", ruta)
            comprobar(f"GET {ruta} → 404 E404", (r.status_code, r.json()) == (404, e404), f"{r.status_code} {r.text[:80]}")
        r = pedir(c, "head", "HEAD", "/health")
        comprobar("HEAD /health → 404 con cuerpo vacío", r.status_code == 404 and r.content == b"", f"{r.status_code} {r.content!r}")

        cuerpo = ('{"m":"' + "A" * (9000 - 8) + '"}').encode()
        assert len(cuerpo) == 9000
        r = pedir(c, "9000 bytes", "POST", "/msg", headers=AUTH, content=cuerpo)
        comprobar("cuerpo de 9000 bytes → 413 E101", r.status_code == 413 and r.json().get("error") == "E101", f"{r.status_code} {r.text[:80]}")

    comprobar("todas las respuestas tardaron < 1 s", not lentas, ", ".join(f"{n}={dt:.2f}s" for n, dt in lentas))
    for nombre, ok, detalle in resultados:
        print(("OK   " if ok else "FALLA"), nombre, "" if ok else f"→ {detalle}")
    return 0 if all(ok for _, ok, _ in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
