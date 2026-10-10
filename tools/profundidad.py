"""Busca la profundidad máxima de anidamiento JSON que acepta el original (E102 = se analizó; E100 = rechazado).

    python tools/profundidad.py

Cuerpo de prueba: '[' * d + ']' * d (≤ 8192 bytes). Un cuerpo válido pero no objeto da E102; si el analizador
tiene límite de profundidad da E100. Búsqueda binaria (~12 requests). Después se «aplanan» en el log las
líneas con listas muy anidadas (si no, Bitacora.leer no puede releerlas).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.comun import Local, aplanar_anidados, cliente_original, usadas  # noqa: E402


def main():
    local = Local()
    resultados = {}
    with cliente_original(max_requests=30) as c:
        c.reset("profundidad JSON: estado inicial")

        def acepta(d: int) -> bool:
            cuerpo = "[" * d + "]" * d
            e = c.raw("POST", "/msg", f"profundidad JSON: lista anidada {d} niveles: ¿E102 (analizada) o E100 (rechazada)?", cuerpo_crudo=cuerpo)
            ok = e.response.get("error") == "E102"
            resultados[d] = (e.id, e.status, e.response.get("error"), local.msg_crudo(cuerpo)[1].get("error"))
            return ok

        lo, hi = 1, 3000  # lo acepta (supuesto), hi rechaza (visto en #4638)
        if acepta(100):
            lo = 100
        else:
            hi = 100
        while hi - lo > 1:
            medio = (lo + hi) // 2
            if acepta(medio):
                lo = medio
            else:
                hi = medio
    n = aplanar_anidados()
    print(f"profundidad máxima aceptada por el original: {lo} (rechaza {hi}); líneas del log aplanadas: {n}")
    for d, (i, st, err, loc) in sorted(resultados.items()):
        print(f"  d={d:5d} #{i} original={st} {err} | reemplazo={loc}")
    print(f"presupuesto usado en la tarea: {usadas()}/3000")


if __name__ == "__main__":
    main()
