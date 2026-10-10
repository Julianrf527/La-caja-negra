"""FR-0153, dimensiones que ni el log ni el replay cubrían: tiempo y escala.

  - Bloqueo E510: ¿caduca con el tiempo? (en v1 no caducó a 8/15/30 s ni con 30 reintentos en ~25 s).
  - Escala: 60 cuentas (v1 llegó a 35) y 105 operaciones (v1 llegó a OP-0040): formato de ids y límites.
Cada respuesta se compara con el reemplazo local (que reproduce la v1).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.control import firmar  # noqa: E402
from tools.comun import Local, cliente_original, resumen  # noqa: E402

P = "FR-0153: "


def paso(c, local, m, hip, difs):
    e = c.msg(firmar(m), P + hip)
    s, r = local.msg_crudo(json.dumps({"m": firmar(m)}, ensure_ascii=False))
    if (e.status, e.response) != (s, r):
        difs.append((e.id, m, (s, r), (e.status, e.response)))
        c.bitacora.concluir(e.id, f"FR-0153 DIFERENCIA: v1/reemplazo={resumen(s, r)} · original ahora={resumen(e.status, e.response)}")
    return e


def tiempo(c, local, difs):
    c.reset(P + "tiempo: estado inicial")
    local.reset()
    for m, h in (("ALTA;Ana", "cuenta origen"), ("ALTA;Beto", "cuenta destino"), ("DEPOSITO;AC-0001;1000000", "saldo")):
        paso(c, local, m, h, difs)
    for i in range(3):
        paso(c, local, "TRANSFER;AC-0001;AC-0002;120000", f"fallo E506 #{i + 1} para bloquear AC-0001", difs)
    ids = []
    for espera, h in ((1, "bloqueo recién creado"), (70, "70 s después"), (130, "200 s después"), (130, "330 s después")):
        time.sleep(espera if espera > 1 else 0)
        e = paso(c, local, "TRANSFER;AC-0001;AC-0002;1", f"¿sigue bloqueada? {h} (v1: no caduca)", difs)
        ids.append((h, e.id, resumen(e.status, e.response)))
    return ids


def escala(c, local, difs):
    c.reset(P + "escala: estado inicial")
    local.reset()
    ultimo = None
    for i in range(60):
        e = paso(c, local, f"ALTA;U{i + 1}", f"alta #{i + 1} (v1 llegó a 35): formato del id y límite de cuentas", difs)
        ultimo = (e.id, resumen(e.status, e.response))
    for i in range(105):
        cuenta = f"AC-{(i % 60) + 1:04d}"
        e = paso(c, local, f"DEPOSITO;{cuenta};{(i % 7 + 1) * 1000}", f"depósito #{i + 1} (v1 llegó a OP-0040): numeración de operaciones", difs)
    return ultimo, (e.id, resumen(e.status, e.response))


if __name__ == "__main__":
    local = Local()
    difs: list = []
    with cliente_original(max_requests=200) as c:
        t = tiempo(c, local, difs)
        for h, i, r in t:
            print(f"  #{i} {h}: {r}")
        e = escala(c, local, difs)
        print("  último ALTA:", e[0], " último DEPOSITO:", e[1])
        print("requests enviados:", c.enviados)
    print("diferencias:", len(difs))
    for i, m, v1, v2 in difs[:20]:
        print(f"  #{i} {m}: v1={v1} v2={v2}")
