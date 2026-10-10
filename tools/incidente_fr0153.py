"""Incidente FR-0153: el original pasó a una «versión 2» con 3 comportamientos distintos.

Este script (1) elige una muestra de experimentos.jsonl que cubre cada regla documentada, (2) la reproduce
contra el ORIGINAL actual con reset antes de cada secuencia y (3) compara status y cuerpo con lo grabado
para el mismo id. No toca app/.

    python tools/incidente_fr0153.py plan          # muestra la muestra elegida y su coste (sin red)
    python tools/incidente_fr0153.py replay        # reproduce contra el original y lista las diferencias

Para que las respuestas grabadas sean reproducibles, de cada secuencia del log se reenvía el reset, los
pasos que cambian el estado (altas, depósitos, transferencias, anulaciones, HALT y los fallos 422 que
alimentan el bloqueo) y los casos objetivo; se omiten las lecturas y los errores sin efecto en el estado.
Cada request nuevo queda en experimentos.jsonl con hipótesis «FR-0153 …» (vía Cliente).
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.comun import LOG, SALIDA, cliente_original  # noqa: E402

# Prefijo de hipótesis de las requests nuevas (v2 ya desplegada, confirmado por X-Req=1 en #7145)
PREFIJO = "FR-0153 v2 confirmado — "

# Casos que el log no puede reproducir con fidelidad (ver tests/regresion/test_regresion.py)
NO_REPRODUCIBLES = {248, 3437, 3645, 4637, 4638}

# Comportamiento documentado -> ids del log que lo ilustran (anexo-referencia-tecnica.md, secciones 2, 3, 6 y 12)
OBJETIVOS: dict[str, list[int]] = {
    # --- 2.1 rutas y auth
    "ruta GET /health": [1], "ruta POST /__reset": [3], "ruta POST /msg": [2],
    "404 ruta/método desconocido": [25, 54, 67], "HEAD → 404 sin cuerpo": [30],
    "E001 sin header / token falso / esquema": [108, 112, 116], "404 antes que 401 (ruta inexistente sin token)": [111],
    # --- 2.5 errores, en orden
    "E599 detenido": [1641, 1644, 1646], "E101 cuerpo grande": [258, 2133], "borde 8192 pasa": [2132],
    "E100 json inválido": [237, 238, 249], "E102 falta m": [239, 241, 246], "E103 falta control": [245, 263],
    "E104 segmento vacío": [264, 267, 2556], "E201 control mal formado": [285, 1713, 1725],
    "E202 control inválido": [284, 1712, 1661], "E301 + espacio final": [1495, 283],
    "E302 aridad": [1649, 1846, 1863, 1882, 1907, 1928], "E303 monto inválido": [1886, 1892, 1943],
    "E304 origen=destino": [1910], "E401 cuenta inexistente": [1865, 2442], "E402 operación inexistente": [1930, 2541],
    "E510 bloqueada": [2142], "E506 límite": [2055, 2011], "E507 saldo insuficiente": [1921, 2524], "E520 confirmación": [1652],
    # --- 3 comandos
    "PING": [2, 281], "PING sin validar control": [268, 270], "ALTA": [6], "CONSULTA": [8], "DEPOSITO": [9], "TRANSFER": [10],
    "ANULA ok y doble": [16, 17], "ANULA depósito": [2455], "ANULA transferencia": [2451],
    "HALT detiene": [1565], "NOTAS": [2821, 2832],
    "DEPOSITO tope 10 dígitos": [1944, 1943], "monto estricto árabe/007": [1896, 1892],
    # --- fórmula de control
    "control N múltiplo de 97 → 98": [5553, 5554, 5558], "control ß / ſ / ı": [3773, 3774, 3777, 3781], "control dígito unicode": [3785],
    "control N vacío": [3789], "PING con args y control malo": [3768],
    # --- límites y titulares
    "límite 100000 pasa": [2056], "límite 100001 falla": [2587], "mismo titular sin límite": [2706, 2707, 2677],
    "distinto titular con límite": [2718, 2719, 2672],
    # --- bloqueo y contadores
    "bloqueo tras 3 fallos": [2139, 2140, 2141, 2142], "deposito desbloquea": [2370, 2371], "bloqueada recibe": [3702],
    "deposito sin bloqueo reinicia contador": [3723], "E507 mismo titular bloquea": [3744],
    "contadores no avanzan con errores": [2482, 2483, 2486, 2490], "saldo negativo por ANULA": [2464, 2476],
    # --- 6 / 12: rarezas y pendientes confirmados
    "sugerencia HELP→HALT": [1507], "sugerencia TOTAL→NOTAS": [2807], "sugerencia desempate": [3797, 3799, 3805, 3809],
    "HALT variantes": [3750, 3753, 3762, 3765], "E304 gana a E401": [3746],
    "JSON NaN / coma / comillas / BOM": [4627, 4628, 4629, 4632], "JSON escape \\u003b y claves duplicadas": [4633, 4634],
    "JSON no objeto": [4635, 4636], "profundidad 20 ok / 21 E100": [4646, 4647], "profundidad con raíz": [4649, 4650],
}


def cargar():
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def es_msg(e) -> bool:
    return e.get("ruta", "/msg") == "/msg" and e.get("metodo", "POST") == "POST"


def comando(e) -> str:
    r = e["request"]
    if isinstance(r, dict) and isinstance(r.get("m"), str):
        return r["m"].split(";")[0].upper()
    return ""


def codigo(e):
    r = e["response"]
    return r.get("error") if isinstance(r, dict) else None


def cambia_estado(e) -> bool:
    """¿Este paso del log altera el estado del servicio (y por tanto hay que reenviarlo para reproducir los siguientes)?"""
    if not es_msg(e):
        return False
    cmd, st, cod = comando(e), e["status"], codigo(e)
    if cmd in ("ALTA", "DEPOSITO", "TRANSFER", "ANULA") and st in (200, 201):
        return True
    if cmd == "HALT" and cod == "E599":
        return True
    if cod in ("E506", "E507"):
        return True  # alimentan el contador de fallos
    return False


def es_reset_real(e) -> bool:
    return e.get("ruta") == "/__reset" and e.get("metodo") == "POST" and e["status"] == 200


def segmentar(lineas):
    """id de línea -> índice (en `lineas`) del reset que abre su secuencia."""
    inicio, actual = {}, None
    for k, e in enumerate(lineas):
        if es_reset_real(e):
            actual = k
        inicio[e["id"]] = actual
    return inicio


def construir_plan(lineas, objetivos: dict[str, list[int]]):
    por_id = {e["id"]: (k, e) for k, e in enumerate(lineas)}
    inicio = segmentar(lineas)
    faltan = []
    por_seg: dict[int, set[int]] = defaultdict(set)
    for beh, ids in objetivos.items():
        for i in ids:
            if i not in por_id or i in NO_REPRODUCIBLES:
                faltan.append((beh, i))
                continue
            if inicio[i] is None:  # antes de cualquier reset: sin estado, se reproduce suelto
                por_seg[-1].add(i)
            else:
                por_seg[inicio[i]].add(i)
    plan = []  # [(k_reset, [indices de línea a reenviar])]
    for k_reset, ids in sorted(por_seg.items()):
        ultimo = max(por_id[i][0] for i in ids)
        if k_reset == -1:
            pasos = sorted(por_id[i][0] for i in ids)
        else:
            pasos = [k for k in range(k_reset + 1, ultimo + 1)
                     if lineas[k]["id"] in ids or (cambia_estado(lineas[k]) and lineas[k]["id"] not in NO_REPRODUCIBLES)]
        plan.append((k_reset, pasos, ids))
    return plan, faltan


def main_plan():
    lineas = cargar()
    plan, faltan = construir_plan(lineas, OBJETIVOS)
    total = sum(1 + len(p) for _, p, _ in plan)  # +1 por el reset de cada secuencia
    print(f"secuencias a reproducir: {len(plan)} · requests estimadas: {total}")
    for k_reset, pasos, ids in plan:
        cab = lineas[k_reset]["id"] if k_reset >= 0 else "(sin reset)"
        print(f"  reset #{cab}: {len(pasos)} pasos, objetivos {sorted(ids)}")
    if faltan:
        print("objetivos no reproducibles o inexistentes:", faltan)
    return plan


# ---------------------------------------------------------------------------------------------- replay
def cuerpo_para(e):
    """Cuerpo crudo a reenviar para una línea del log (el log guarda `request` ya parseado)."""
    req = e["request"]
    if es_msg(e) and req is None:
        return "null"  # el log guarda el cuerpo 'null' como None (#239)
    if req is None:
        return None
    if isinstance(req, str):
        return req
    compacto = isinstance(req, dict) and list(req) == ["m"] and isinstance(req["m"], str) and len(req["m"]) > 1000
    return json.dumps(req, ensure_ascii=False, separators=(",", ":") if compacto else (", ", ": "))


def reenviar(c, e, hip):
    metodo, ruta = e.get("metodo", "POST"), e.get("ruta", "/msg")
    auth = e.get("auth")
    if auth is None:
        from helper.cliente import TOKEN_PROPIO

        valor = TOKEN_PROPIO
    elif auth == "(sin header)":
        valor = None
    else:
        valor = auth.replace("<token>", c.token)
    req = e["request"]
    if es_msg(e) and isinstance(req, dict) and list(req) == ["m"] and isinstance(req["m"], str) and len(req["m"]) <= 1000:
        return c.raw("POST", "/msg", hip, cuerpo={"m": req["m"]}, auth=valor)
    return c.raw(metodo, ruta, hip, cuerpo_crudo=cuerpo_para(e), auth=valor)


def igual(a_status, a_resp, b_status, b_resp) -> bool:
    return a_status == b_status and a_resp == b_resp


def resumen_req(e) -> str:
    r = e["request"]
    base = str(r["m"]) if isinstance(r, dict) and "m" in r else json.dumps(r, ensure_ascii=False)
    base = base[:70] + ("…" if len(base) > 70 else "")
    return base if es_msg(e) else f"{e.get('metodo')} {e.get('ruta')} {base if r is not None else ''}".strip()


def main_recuperar(base: int):
    """Reconstruye las comparaciones de un replay interrumpido a partir del log (líneas FR-0153 con id > base)."""
    import re

    lineas = cargar()
    por_id = {e["id"]: e for e in lineas}
    out = []
    for e in lineas:
        m = re.match(r"FR-0153(?::| v2 confirmado —) replay de #(\d+) ", e.get("hipotesis", ""))
        if e["id"] > base and m and int(m.group(1)) in por_id:
            v1 = por_id[int(m.group(1))]
            out.append({"id": v1["id"], "nuevo_id": e["id"], "request": resumen_req(v1), "v1": {"status": v1["status"], "response": v1["response"]},
                        "v2": {"status": e["status"], "response": e["response"]}, "igual": igual(v1["status"], v1["response"], e["status"], e["response"])})
    previo = SALIDA / "fr0153_recuperado.json"
    previo.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"recuperadas {len(out)} comparaciones; diferencias: {sum(not r['igual'] for r in out)}")
    for r in out:
        if not r["igual"]:
            print(f"DIFERENCIA #{r['id']} (nuevo #{r['nuevo_id']}) {r['request']}\n   v1: {r['v1']['status']} {json.dumps(r['v1']['response'], ensure_ascii=False)}\n   v2: {r['v2']['status']} {json.dumps(r['v2']['response'], ensure_ascii=False)}")


def objetivos_densos(lineas, resets: list[int]) -> dict[str, list[int]]:
    """Todos los pasos de las secuencias del log que empiezan en los resets dados (cobertura densa de formas)."""
    objetivos, actual = {}, None
    for e in lineas:
        if es_reset_real(e):
            actual = e["id"] if e["id"] in resets else None
            if actual:
                objetivos[f"denso #{actual}"] = []
        elif actual and e["id"] not in NO_REPRODUCIBLES:
            objetivos[f"denso #{actual}"].append(e["id"])
    return objetivos


def main_replay(reset_minimo: int = 0, base: int | None = None, densos: list[int] | None = None):
    """Reproduce el plan. `reset_minimo` retoma desde la secuencia cuyo reset tiene ese id o más;
    `base` es el último id del log anterior al replay (para ignorar las líneas del propio replay)."""
    lineas = cargar()
    if base is not None:
        lineas = [e for e in lineas if e["id"] <= base]
    objetivos = objetivos_densos(lineas, densos) if densos else OBJETIVOS
    plan, faltan = construir_plan(lineas, objetivos)
    plan = [p for p in plan if p[0] < 0 and reset_minimo == 0 or p[0] >= 0 and lineas[p[0]]["id"] >= reset_minimo]
    por_id = {e["id"]: e for e in lineas}
    objetivo_de = defaultdict(list)
    for beh, ids in objetivos.items():
        for i in ids:
            objetivo_de[i].append(beh)
    resultados, diferencias = [], []
    with cliente_original(max_requests=500) as c:
        for k_reset, pasos, ids in plan:
            ref = lineas[k_reset]["id"] if k_reset >= 0 else "inicio"
            c.reset(f"{PREFIJO}reset antes de reproducir la secuencia del log que empieza en #{ref}")
            for k in pasos:
                e = lineas[k]
                hip = (f"{PREFIJO}replay de #{e['id']} contra el original actual (¿v2 responde igual que la v1 grabada?)"
                       + (f" [{'; '.join(objetivo_de[e['id']])}]" if e["id"] in objetivo_de else ""))
                n = reenviar(c, e, hip)
                ok = igual(e["status"], e["response"], n.status, n.response)
                reg = {"id": e["id"], "nuevo_id": n.id, "request": resumen_req(e), "objetivo": e["id"] in objetivo_de,
                       "comportamientos": objetivo_de.get(e["id"], []),
                       "v1": {"status": e["status"], "response": e["response"]},
                       "v2": {"status": n.status, "response": n.response}, "igual": ok}
                resultados.append(reg)
                if not ok:
                    diferencias.append(reg)
                    c.bitacora.concluir(n.id, f"{PREFIJO}DIFERENCIA con #{e['id']}: v1={e['status']} {json.dumps(e['response'], ensure_ascii=False)[:120]} "
                                              f"→ v2={n.status} {json.dumps(n.response, ensure_ascii=False)[:120]}")
        enviados = c.enviados
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / ("fr0153_denso.json" if densos else "fr0153_replay.json")).write_text(json.dumps({"resultados": resultados, "diferencias": diferencias}, ensure_ascii=False, indent=1), encoding="utf-8")
    objetivos = [r for r in resultados if r["objetivo"]]
    print(f"requests al original: {enviados} · líneas comparadas: {len(resultados)} (objetivo: {len(objetivos)}) · diferencias: {len(diferencias)}")
    for r in diferencias:
        print(f"\nDIFERENCIA en #{r['id']} (nuevo #{r['nuevo_id']}) {r['comportamientos']}\n  request: {r['request']}")
        print(f"  v1: {r['v1']['status']} {json.dumps(r['v1']['response'], ensure_ascii=False)}")
        print(f"  v2: {r['v2']['status']} {json.dumps(r['v2']['response'], ensure_ascii=False)}")
    if faltan:
        print("no reproducibles/ausentes:", faltan)


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if modo == "replay":
        main_replay(*(int(x) for x in sys.argv[2:4]))
    elif modo == "denso":
        base = cargar()[-1]["id"]
        main_replay(0, base, [int(x) for x in sys.argv[2:]])
    elif modo == "plan-denso":
        ls = cargar()
        pl, _ = construir_plan(ls, objetivos_densos(ls, [int(x) for x in sys.argv[2:]]))
        print("secuencias:", len(pl), "requests estimadas:", sum(1 + len(p) for _, p, _ in pl))
    elif modo == "recuperar":
        main_recuperar(int(sys.argv[2]))
    else:
        main_plan()
