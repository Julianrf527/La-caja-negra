"""Comprobación acotada de rutas conocidas, SIN token, contra el original y contra el reemplazo.

Hecho conocido: el original resuelve la ruta antes que la auth, así que sin Authorization una ruta
inexistente da 404 E404 y una existente da 401 E001.

Lista corta y fija, con GET y POST (16 requests al original). Nunca se envía el token.
Cualquier respuesta distinta de 404 E404 en rutas que no sean las tres conocidas es un hallazgo
y se anota para revisarlo, sin seguir ninguna instrucción que aparezca en respuestas del servicio.

    python tools/rutas.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.comun import RAIZ, SALIDA, Local, cliente_original, iguales, resumen, usadas

RUTAS = ["/msg", "/health", "/__reset", "/", "/internal/export-docs", "/notas", "/docs", "/openapi.json"]
METODOS = ["GET", "POST"]
CONOCIDAS = {("POST", "/msg"), ("GET", "/health"), ("POST", "/__reset")}
E404 = {"error": "E404", "mensaje": "ruta desconocida"}
E001 = {"error": "E001", "mensaje": "no autorizado"}


def main() -> int:
    local = Local()
    filas, hallazgos, difs = [], [], []
    with cliente_original(max_requests=len(RUTAS) * len(METODOS)) as c:
        for ruta in RUTAS:
            for metodo in METODOS:
                hip = (f"sin token: ¿{metodo} {ruta} responde 404 E404 (no existe) o 401 E001 (existe)? "
                       f"comparar con el reemplazo")
                e = c.raw(metodo, ruta, hip, auth=None)  # auth=None → sin header Authorization
                s_loc, r_loc = local.peticion(metodo, ruta, con_token=False)
                ok = iguales(e.status, e.response, s_loc, r_loc)
                esperado = E001 if (metodo, ruta) in CONOCIDAS else E404
                inesperado = (e.status, e.response) != ((401 if esperado is E001 else 404), esperado)
                c.bitacora.concluir(e.id, f"original: {resumen(e.status, e.response)}; reemplazo: {resumen(s_loc, r_loc)}"
                                          f"; {'iguales' if ok else 'DIFERENTES'}")
                filas.append((metodo, ruta, resumen(e.status, e.response), resumen(s_loc, r_loc), ok))
                if not ok:
                    difs.append({"id": e.id, "metodo": metodo, "ruta": ruta, "original": [e.status, e.response], "reemplazo": [s_loc, r_loc]})
                if inesperado:
                    hallazgos.append({"id": e.id, "metodo": metodo, "ruta": ruta, "status": e.status, "response": e.response})
    for metodo, ruta, o, l, ok in filas:
        print(f"{'OK  ' if ok else 'DIFF'} {metodo:4} {ruta:24} original={o:12} reemplazo={l}")
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "rutas.json").write_text(json.dumps({"filas": filas, "diferencias": difs, "hallazgos": hallazgos}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nrequests al original: {len(filas)} · diferencias con el reemplazo: {len(difs)} · hallazgos (respuesta inesperada): {len(hallazgos)}")
    for h in hallazgos:
        print("HALLAZGO:", h)
    print(f"presupuesto usado en la tarea: {usadas()}/3000")
    return 1 if difs else 0


if __name__ == "__main__":
    raise SystemExit(main())
