"""Reproduce test-original-app/experimentos.jsonl contra la app (sin red, con TestClient).

Respeta el orden del log, los resets donde el log los hace, el método, la ruta y la auth de cada línea.
Compara con las reglas del reto: mismo status y mismo cuerpo (JSON: claves en cualquier orden;
si no es JSON, texto exacto). Imprime el porcentaje de coincidencia y los ids que fallan.

Limitaciones conocidas del log (anexo, sección 9) que se excluyen de la comparación:
- #248: el log guarda `request` ya parseado, así que el string JSON "PING;64" (E102) es
  indistinguible del texto plano PING;64 (#249, E100). Se prueba a mano en test_orden.py.
- Los cuerpos de tamaño exacto (#2119-#2133) se reconstruyen en formato compacto, como los generó el explorador.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

from tests.conftest import TOKEN

LOG = Path(__file__).parents[2] / "test-original-app/experimentos.jsonl"
EXCLUIDOS = {
    n: "string JSON indistinguible de texto plano en el log (anexo 9)"
    for n in (248, 3437, 3645)  # cuerpo "PING;1" entre comillas (E102) que el log guarda como texto
}
EXCLUIDOS[4637] = "1e999 se guarda como inf y al reenviarlo se serializa como Infinity (se prueba en test_confirmados.py)"


def _cuerpo(e: dict) -> bytes | None:
    metodo, ruta, req = e.get("metodo", "POST"), e.get("ruta", "/msg"), e["request"]
    if ruta == "/msg" and metodo == "POST" and req is None:
        return b"null"  # el log guarda 'null' como None (#239)
    if req is None:
        return None
    if isinstance(req, str):
        return req.encode("utf-8")
    compacto = isinstance(req, dict) and list(req) == ["m"] and isinstance(req["m"], str) and len(req["m"]) > 1000
    texto = json.dumps(req, ensure_ascii=False, separators=(",", ":") if compacto else (", ", ": "))
    return texto.encode("utf-8")


def _cabeceras(e: dict) -> dict:
    auth = e.get("auth")
    if auth is None:
        return {"Authorization": f"Bearer {TOKEN}"}
    if auth == "(sin header)":
        return {}
    return {"Authorization": auth.replace("<token>", TOKEN)}


def _iguales(esperado, status_esperado: int, r) -> bool:
    if r.status_code != status_esperado:
        return False
    if isinstance(esperado, str):  # el original no devolvió JSON: texto exacto
        return r.text == esperado
    try:
        return r.json() == esperado
    except ValueError:
        return False


def _comportamiento_v2(e: dict) -> bool:
    """Señales inequívocas del original v2: saldo como texto, E510=423, o E506 con monto <=100000."""
    r = e["response"]
    if isinstance(r, dict):
        if isinstance(r.get("saldo"), str):
            return True
        if r.get("error") == "E510" and e.get("status") == 423:
            return True
        if r.get("error") == "E506":
            req = e.get("request")
            if isinstance(req, dict) and isinstance(req.get("m"), str):
                partes = req["m"].split(";")
                if len(partes) >= 4 and partes[3].isdigit() and 50001 <= int(partes[3]) <= 100000:
                    return True
    return False


def test_regresion_contra_experimentos(capsys, monkeypatch):
    monkeypatch.setattr("app.captura.registrar", lambda *a, **k: None)  # sin ruido de CAPTURA
    lineas = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    # El original cambió a v2 durante el día (switch FR-0153). El corte se detecta empíricamente: el
    # primer id con comportamiento v2 observado. Antes de ese id el original era v1 (aunque pi ya estuviera
    # investigando FR-0153); desde ese id, v2. Cada línea se reproduce contra su perfil.
    primer_v2 = min((e["id"] for e in lineas if _comportamiento_v2(e)), default=None)
    fallos, comparados, sin_token_health = [], 0, []
    with TestClient(app) as client:
        for e in lineas:
            perfil = "v2" if (primer_v2 is not None and e["id"] >= primer_v2) else "v1"
            monkeypatch.setenv("VERSION_REGLAS", perfil)
            cuerpo = _cuerpo(e)
            r = client.request(e.get("metodo", "POST"), e.get("ruta", "/msg"), content=cuerpo, headers=_cabeceras(e))
            if e["id"] in EXCLUIDOS:
                continue
            if (e.get("metodo"), e.get("ruta")) in (("GET", "/health"), ("POST", "/__reset")) and e["status"] == 401:
                sin_token_health.append(e["id"])  # /health y /__reset son públicos por contrato; el original daba 401
                continue
            comparados += 1
            if not _iguales(e["response"], e["status"], r):
                fallos.append((e, r))

    pct = 100 * (comparados - len(fallos)) / comparados
    with capsys.disabled():
        print(f"\nREGRESIÓN: {comparados - len(fallos)}/{comparados} coinciden ({pct:.2f} %); excluidos: {sorted(EXCLUIDOS)}; GET /health y POST /__reset sin token válido (públicos por contrato, 200): {len(sin_token_health)} líneas omitidas")
        print("ids que fallan:", [e["id"] for e, _ in fallos])
        for e, r in fallos[:40]:
            req = e["request"]["m"] if isinstance(e["request"], dict) and "m" in e["request"] else str(e["request"])[:60]
            print(f"  #{e['id']} {e.get('metodo','POST')} {e.get('ruta','/msg')} {req!r}: "
                  f"esperado {e['status']} {json.dumps(e['response'], ensure_ascii=False)[:80]} | "
                  f"obtenido {r.status_code} {r.text[:80]}")
    assert not fallos, f"{len(fallos)} diferencias; ver la lista impresa"
