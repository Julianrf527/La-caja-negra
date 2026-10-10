"""FR-0153: investigación de los 3 cambios de la v2 (ya desplegada: X-Req = 1 en #7145).

El replay (tools/incidente_fr0153.py) encontró estas diferencias de origen (las demás son efecto en cascada):
  1. CONSULTA: "saldo" pasó de número entero a texto con dos decimales ("0.00", "-9.00" donde antes 0, -900).
  2. TRANSFER: el límite bajó (100000 y 60000 dan E506; 40000 sigue pasando).
  3. E510: ahora 423 y con el campo "intentos" (antes 409 sin campo).

Uso:  python tools/fr0153_v2.py saldo|limite|bloqueo
Cada request va por Cliente (queda en experimentos.jsonl con hipótesis «FR-0153 v2 confirmado — …»).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.control import firmar  # noqa: E402
from tools.comun import cliente_original  # noqa: E402

P = "FR-0153 v2 confirmado — "


def q(c, m, hip, mostrar=True):
    e = c.msg(firmar(m), P + hip)
    if mostrar:
        print(f"  #{e.id} {m:44} → {e.status} {json.dumps(e.response, ensure_ascii=False)}")
    return e


def saldo(c):
    c.reset(P + "saldo: estado inicial")
    # una cuenta por saldo para aislar cada formato
    casos = [1, 5, 50, 99, 100, 101, 1000, 12345, 100000, 1000000, 9999999999]
    for i, v in enumerate(casos, 1):
        q(c, f"ALTA;S{i}", f"saldo: crear cuenta {i}", mostrar=False)
    q(c, "CONSULTA;AC-0001", "saldo: cuenta nueva sin depósitos (formato de 0)")
    for i, v in enumerate(casos, 1):
        q(c, f"DEPOSITO;AC-{i:04d};{v}", f"saldo: depositar {v} en AC-{i:04d}", mostrar=False)
        q(c, f"CONSULTA;AC-{i:04d}", f"saldo: formato del saldo {v}")
    # negativos: depositar, gastar y anular el depósito
    q(c, "ALTA;N1", "saldo: cuenta para saldo negativo", mostrar=False)
    q(c, "DEPOSITO;AC-0012;1", "saldo: depósito de 1 (OP siguiente)", mostrar=False)
    q(c, "ALTA;N2", "saldo: destino", mostrar=False)
    q(c, "TRANSFER;AC-0012;AC-0013;1", "saldo: gastar el depósito", mostrar=False)


def saldo_negativos(c, op_dep: str):
    q(c, f"ANULA;{op_dep}", "saldo: anular el depósito ya gastado → saldo -1")
    q(c, "CONSULTA;AC-0012", "saldo: formato de -1")
    q(c, "CONSULTA;AC-0013", "saldo: formato de 1 en el destino")


def limite(c):
    c.reset(P + "límite: estado inicial")
    for m, h in (("ALTA;Ana", "origen"), ("ALTA;Beto", "destino"), ("DEPOSITO;AC-0001;9999999999", "saldo enorme")):
        q(c, m, f"límite: {h}", mostrar=False)
    lo, hi = 40000, 60000  # 40000 pasa (#7154), 60000 falla (#7260)
    sondeos = []

    def pasa(monto):
        e = q(c, f"TRANSFER;AC-0001;AC-0002;{monto}", f"límite: ¿pasa transferir {monto}? (búsqueda binaria entre 40000 y 60000)", mostrar=False)
        ok = e.status == 200
        sondeos.append((monto, e.id, e.status, (e.response or {}).get("error")))
        if not ok:  # no dejar que los fallos seguidos bloqueen la cuenta
            q(c, "TRANSFER;AC-0001;AC-0002;1", "límite: transferencia mínima para reiniciar el contador de fallos", mostrar=False)
        return ok

    while hi - lo > 1:
        medio = (lo + hi) // 2
        if pasa(medio):
            lo = medio
        else:
            hi = medio
    for s in sondeos:
        print(f"  #{s[1]} {s[0]:>6} → {s[2]} {s[3] or ''}")
    print(f"  límite: pasa {lo}, falla {hi}")
    return lo, hi


def limite_variaciones(c, lo):
    # ¿depende del saldo? origen con saldo justo
    c.reset(P + "límite: ¿depende del saldo del origen?")
    for m in ("ALTA;Ana", "ALTA;Beto"):
        q(c, m, "límite/saldo: crear", mostrar=False)
    q(c, f"DEPOSITO;AC-0001;{lo + 1}", f"límite/saldo: saldo justo {lo + 1}", mostrar=False)
    q(c, f"TRANSFER;AC-0001;AC-0002;{lo}", f"límite/saldo: transferir {lo} con saldo {lo + 1}")
    q(c, f"TRANSFER;AC-0002;AC-0001;{lo}", f"límite/saldo: devolver {lo} (destino con saldo {lo})")
    # ¿sigue la excepción de mismo titular?
    c.reset(P + "límite: ¿sigue la excepción de mismo titular?")
    for m in ("ALTA;Ana", "ALTA;Ana", "DEPOSITO;AC-0001;9999999999"):
        q(c, m, "límite/titular: preparar", mostrar=False)
    q(c, "TRANSFER;AC-0001;AC-0002;100000", "límite/titular: 100000 entre cuentas del mismo titular")
    q(c, "TRANSFER;AC-0001;AC-0002;2000000", "límite/titular: 2000000 entre cuentas del mismo titular")
    # ¿cambia el orden E506/E507? (monto sobre el límite y sin saldo)
    c.reset(P + "límite: orden E506 / E507")
    for m in ("ALTA;Ana", "ALTA;Beto", "DEPOSITO;AC-0001;10"):
        q(c, m, "límite/orden: preparar", mostrar=False)
    q(c, f"TRANSFER;AC-0001;AC-0002;{lo + 1}", f"límite/orden: monto {lo + 1} > límite y > saldo 10")


def bloqueo(c):
    c.reset(P + "bloqueo: estado inicial")
    for m in ("ALTA;Ana", "ALTA;Beto", "DEPOSITO;AC-0001;1000"):
        q(c, m, "bloqueo: preparar", mostrar=False)
    # fallos E507 (sin depender del límite): AC-0002 no tiene saldo
    for i in range(3):
        q(c, "TRANSFER;AC-0002;AC-0001;5", f"bloqueo: fallo E507 #{i + 1} de AC-0002 (sin saldo)")
    for i in range(4):
        q(c, "TRANSFER;AC-0002;AC-0001;5", f"bloqueo: intento #{i + 1} con la cuenta bloqueada: ¿cuenta «intentos»?")
    q(c, "TRANSFER;AC-0002;AC-0001;99999999", "bloqueo: bloqueada y monto enorme (¿E510 antes que E506?)")
    q(c, "TRANSFER;AC-0002;AC-0099;1", "bloqueo: bloqueada y destino inexistente (¿E401 antes que E510?)")
    q(c, "TRANSFER;AC-0002;AC-0002;1", "bloqueo: bloqueada y origen=destino")
    q(c, "TRANSFER;AC-0002;AC-0001;abc", "bloqueo: bloqueada y monto inválido")
    q(c, "CONSULTA;AC-0002", "bloqueo: CONSULTA de la cuenta bloqueada")
    q(c, "DEPOSITO;AC-0002;5", "bloqueo: depósito que desbloquea")
    for i in range(3):
        q(c, "TRANSFER;AC-0002;AC-0001;99", f"bloqueo: tras desbloquear, fallo E507 #{i + 1}")
    q(c, "TRANSFER;AC-0002;AC-0001;1", "bloqueo: primer intento bloqueado tras el nuevo bloqueo: ¿intentos vuelve a 1?")
    # otra cuenta bloqueada: ¿el contador es por cuenta?
    q(c, "ALTA;Cata", "bloqueo: tercera cuenta", mostrar=False)
    for i in range(3):
        q(c, "TRANSFER;AC-0003;AC-0001;5", f"bloqueo: fallo E507 #{i + 1} de AC-0003")
    q(c, "TRANSFER;AC-0003;AC-0001;5", "bloqueo: primer intento bloqueado de AC-0003 (¿intentos propio?)")
    q(c, "TRANSFER;AC-0002;AC-0001;1", "bloqueo: AC-0002 bloqueada otra vez: ¿su contador sigue aparte?")


if __name__ == "__main__":
    modo = sys.argv[1]
    with cliente_original(max_requests=int(sys.argv[2]) if len(sys.argv) > 2 else 120) as c:
        if modo == "saldo":
            saldo(c)
            # el id del depósito de 1 en AC-0012 es el 12.º depósito → OP-0012 (se anula tras gastarlo)
            saldo_negativos(c, "OP-0012")
        elif modo == "limite":
            lo, hi = limite(c)
            limite_variaciones(c, lo)
        elif modo == "bloqueo":
            bloqueo(c)
        print("requests enviados:", c.enviados)
