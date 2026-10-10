"""Confirma contra el original los puntos pendientes (docs/diseno.md, sección 12 y anexo).

    python tools/confirmar.py [grupo ...]      # grupos: bloqueo, titular, e304, sugerencia, halt, unicode, ping

Cada experimento es una secuencia (reset + mensajes) que se ejecuta contra el original (Cliente, con
hipótesis, queda en experimentos.jsonl) y contra el reemplazo local; se imprime paso a paso y se
guarda en tools/salida/pendientes.json. El primer id del log de cada experimento sirve de evidencia.
"""

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config import reglas  # noqa: E402
from app.core.control import firmar  # noqa: E402
from app.core.sugerencia import levenshtein  # noqa: E402
from tools.comun import SALIDA, Local, cliente_original, iguales, resumen, usadas  # noqa: E402


def S(m):  # mensaje firmado
    return ("msg", firmar(m))


def R(cuerpo):  # cuerpo crudo (no necesariamente JSON)
    return ("raw", cuerpo)


def M(m):  # mensaje sin firmar (se envía tal cual)
    return ("msg", m)


EXPERIMENTOS: dict[str, list[tuple[str, str, list]]] = {}


def exp(grupo, nombre, hipotesis, pasos):
    EXPERIMENTOS.setdefault(grupo, []).append((nombre, hipotesis, pasos))


BASE = [S("ALTA;Ana"), S("ALTA;Beto"), S("DEPOSITO;AC-0001;1000")]
BLOQUEAR_2 = [S("TRANSFER;AC-0002;AC-0001;5")] * 3 + [S("TRANSFER;AC-0002;AC-0001;5")]  # 3 fallos + comprobación E510

# ---- bloqueo
exp("bloqueo", "recibe-bloqueada", "una cuenta bloqueada puede recibir transferencias",
    BASE + BLOQUEAR_2 + [S("TRANSFER;AC-0001;AC-0002;5"), S("CONSULTA;AC-0002")])
exp("bloqueo", "deposito-reinicia-contador-al-desbloquear", "el depósito que desbloquea pone a cero el contador de fallos",
    BASE + BLOQUEAR_2 + [S("DEPOSITO;AC-0002;1"), S("TRANSFER;AC-0002;AC-0001;5"), S("TRANSFER;AC-0002;AC-0001;1")])
exp("bloqueo", "deposito-sin-bloqueo-no-reinicia", "un depósito a una cuenta con 2 fallos (no bloqueada) pone a cero el contador",
    BASE + [S("TRANSFER;AC-0002;AC-0001;5")] * 2 + [S("DEPOSITO;AC-0002;100"), S("TRANSFER;AC-0002;AC-0001;500"), S("TRANSFER;AC-0002;AC-0001;1")])
exp("bloqueo", "fallos-tras-desbloqueo", "tras desbloquear con depósito, ¿cuántos fallos hacen falta para bloquear de nuevo?",
    BASE + BLOQUEAR_2 + [S("DEPOSITO;AC-0002;1")] + [S("TRANSFER;AC-0002;AC-0001;5")] * 3 + [S("TRANSFER;AC-0002;AC-0001;1")])

# ---- mismo titular
exp("titular", "e507-mismo-titular-bloquea", "los E507 entre cuentas del mismo titular cuentan para el bloqueo",
    [S("ALTA;Ana"), S("ALTA;Ana"), S("DEPOSITO;AC-0001;10")] + [S("TRANSFER;AC-0001;AC-0002;999999999")] * 3 + [S("TRANSFER;AC-0001;AC-0002;1")])

# ---- E304 vs E401
exp("e304", "misma-inexistente", "origen = destino = cuenta inexistente: ¿E304 o E401?",
    [S("TRANSFER;AC-0099;AC-0099;5"), S("TRANSFER;AC-0099;AC-0099;abc"), S("TRANSFER;AC-0001;AC-0001;5")])

# ---- HALT: variantes de la confirmación
for arg in ["01", "+1", " 1", "1 ", "1.0", "１"]:
    exp("halt", f"halt-{arg!r}", f"HALT con confirmación {arg!r}: ¿detiene (E599 después) o E520?", [S(f"HALT;{arg}"), S("PING")])

# ---- ping con argumentos y control inválido
exp("ping", "ping-args-control-malo", "PING con argumentos y control inválido: ¿E302 o pong?",
    [M("PING;a;X"), M("PING;a;b;X"), M("PING;a;"), S("PING;a")])

# ---- unicode: cómo se normaliza el cuerpo para el control (R-08 del anexo)
def _con_control(cuerpo, control):
    return M(f"{cuerpo};{control}")


exp("unicode", "eszett", "'ß' en el cuerpo: ¿str.upper() (→SS) o se ignora?",
    [S("ß;x"), _con_control("ß;x", 26), S("ß;ß;x")])
exp("unicode", "s-larga", "'ſ' (s larga) en un comando: ¿se normaliza a S?",
    [S("conſulta;AC-0001"), _con_control("conſulta;AC-0001", 14), S("CONSULTA;AC-0001")])
exp("unicode", "i-sin-punto", "'ı' (i sin punto) en un comando: ¿se normaliza a I?",
    [S("pıng"), _con_control("pıng", 0), M("pıng;1")])
exp("unicode", "digito-unicode", "dígitos no ASCII en el cuerpo: ¿cuentan para N?",
    [S("x;٣"), S("x;3"), S("CONSULTA;AC-000٣")])
exp("unicode", "n-vacio", "cuerpo sin letras ni dígitos (N=0): ¿qué control acepta?",
    [M("ÑÑ;1"), M("ÑÑ;97"), M("-;1"), M("-;97"), M("-;0"), M("-;50"), M("-;96")])


# ---- JSON: bordes del E100/E102 (qué acepta el analizador del original)
exp("json", "bordes", "qué cuerpos acepta el analizador JSON del original (E100 vs aceptado)", [
    R('{"m":"PING;1","x":NaN}'), R('{"m":"PING;64",}'), R("{'m':'PING;64'}"), R('{"m":"PING;64"} x'),
    R('{"m":"PING;64"}\n\n'), R('\ufeff{"m":"PING;64"}'), R('{"m":"PING\\u003b64"}'), R('{"m":"PING;64","m":1}'),
    R("1"), R("true"), R('{"m":"PING;64","n":1e999}'),
    R('{"m":"PING;64"}\x00'), R('{\n"m"\t:\r"PING;64"}'),
])


# ---- JSON: ¿el objeto raíz cuenta como un nivel de profundidad? (límite hallado con tools/profundidad.py: 20 niveles)
exp("profundidad", "objeto-raiz", "profundidad con objeto raíz: 19 y 20 listas dentro de {\"m\":..}", [
    R('{"m":"PING;64","a":' + "[" * 19 + "]" * 19 + "}"), R('{"m":"PING;64","a":' + "[" * 20 + "]" * 20 + "}"),
    R('{"m":"PING;64","a":' + '{"a":' * 18 + "1" + "}" * 18 + "}"), R('{"m":"PING;64","a":' + '{"a":' * 19 + "1" + "}" * 19 + "}"),
    R('{"m":"PING;64","a":' + '{"a":' * 20 + "1" + "}" * 20 + "}"),
])


# ---- cuerpos con N múltiplo de 97: el control válido es 98 (ISO 7064 MOD 97-10)
exp("control98", "n-multiplo-de-97", "con N múltiplo de 97 el control válido es 98",
    [M("RETIRA;98"), M("ALTA;HD;98"), M("ALTA;KY;98"), M("CONSULTA;AC-0001;98"), S("ALTA;LV"), M("ÑÑ;98"), M("-;98")])


# ---- sugerencia: desempate
def _empates(maximo=8):
    """Palabras a distancia ≤ 2 de dos o más comandos por igual, con empates distintos entre sí y
    donde 'el primero de la lista' y 'el primero alfabético' darían respuestas distintas."""
    cmds = list(reglas.activo()["comandos"])
    letras = sorted({ch for c in cmds for ch in c})
    vistos, salida = set(), []
    for n in (3, 4):
        for t in itertools.product(letras, repeat=n):
            w = "".join(t)
            ds = sorted((levenshtein(w, c), c) for c in cmds)
            if ds[0][0] > 2 or w in cmds:
                continue
            ties = [c for c in cmds if levenshtein(w, c) == ds[0][0]]  # en el orden de la lista
            if len(ties) < 2 or tuple(ties) in vistos:
                continue
            vistos.add(tuple(ties))
            salida.append((w, ties))
            if len(salida) >= 60:
                break
        if len(salida) >= 60:
            break
    salida.sort(key=lambda x: (x[1][0] == min(x[1]), len(x[0])))  # primero los que discriminan
    return salida[:maximo]


def _registrar_sugerencias():
    for w, ties in _empates():
        exp("sugerencia", f"empate-{w}", f"empate de sugerencia para {w!r} entre {ties}: ¿cuál elige?", [S(f"{w};AC-0001")])


_registrar_sugerencias()


def ejecutar(grupos):
    SALIDA.mkdir(exist_ok=True)
    local = Local()
    informe = []
    antes = usadas()
    with cliente_original(max_requests=400) as c:
        for g in grupos:
            for nombre, hipotesis, pasos in EXPERIMENTOS[g]:
                c.reset(f"confirmar {g}/{nombre}: {hipotesis}")
                local.reset()
                filas, primer_id = [], None
                for k, (tipo, v) in enumerate(pasos):
                    hip = f"confirmar {g}/{nombre} paso {k}: {hipotesis}"
                    if tipo == "raw":
                        e = c.raw("POST", "/msg", hip, cuerpo_crudo=v)
                        s, r = local.msg_crudo(v)
                    else:
                        e = c.msg(v, hip)
                        s, r = local.msg_crudo(json.dumps({"m": v}, ensure_ascii=False))
                    primer_id = primer_id or e.id
                    ok = iguales(e.status, e.response, s, r)
                    c.bitacora.concluir(e.id, f"original {resumen(e.status, e.response)} · reemplazo {resumen(s, r)} · {'igual' if ok else 'DIFERENTE'}")
                    filas.append({"id": e.id, "m": v, "original": resumen(e.status, e.response),
                                  "sugerencia": (e.response or {}).get("sugerencia") if isinstance(e.response, dict) else None,
                                  "reemplazo": resumen(s, r), "igual": ok})
                informe.append({"grupo": g, "nombre": nombre, "hipotesis": hipotesis, "pasos": filas})
                marca = "OK  " if all(f["igual"] for f in filas) else "DIFF"
                print(f"{marca} [{g}] {nombre}: {hipotesis}")
                for f in filas:
                    sug = f" sug={f['sugerencia']}" if f["sugerencia"] else ""
                    print(f"      #{f['id']} {f['m'][:44]!r:48} orig={f['original']}{sug} | rep={f['reemplazo']}{'' if f['igual'] else '   <-- DIFERENTE'}")
    ruta = SALIDA / "pendientes.json"
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
    ruta.write_text(json.dumps(previo + informe, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nrequests usadas en esta ejecución: {usadas() - antes} · presupuesto total de la tarea: {usadas()}/3000")


if __name__ == "__main__":
    pedidos = sys.argv[1:] or list(EXPERIMENTOS)
    ejecutar(pedidos)
