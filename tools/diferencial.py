"""Pruebas diferenciales: secuencias aleatorias reproducibles contra el original y el reemplazo.

    python tools/diferencial.py --semilla 1 --n 100 [--desde 0] [--max-requests 900] [--seguir] [--limpiar]

Cada secuencia empieza con reset y tiene entre 2 y 12 mensajes (mezcla de los 8 comandos, controles
válidos calculados con la fórmula y casos borde de las reglas del anexo). Se ejecuta contra el original
(vía Cliente, queda en experimentos.jsonl con su hipótesis) y contra el reemplazo local (TestClient,
con su propio reset). Se compara status y cuerpo con las reglas del reto.

Por defecto cada secuencia se detiene en la primera diferencia (las siguientes serían ruido por estado
distinto); con --seguir se ejecuta entera. Las diferencias se agregan a tools/salida/diferencias.jsonl.
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.control import esperado, firmar  # noqa: E402
from tools.comun import SALIDA, Local, cliente_original, iguales, resumen, usadas  # noqa: E402

NOMBRES = ["Ana", "Ana", "Ana", "Beto", "ana", "ANA", "Ana Maria", "123", "Ñandú", "AC-0001", "Lucia", "x"]
MONTOS_OK = ["1", "5", "100", "1000", "50000", "99999", "100000", "100001", "120000", "2000000", "9999999999"]
MONTOS_MAL = ["0", "-5", "1.5", "abc", "007", "+5", " 5", "10000000000", "1e3", "5 ", "1,5", ""]
INEX_CUENTA = ["AC-0099", "AC-9999", "ac-0001", "AC-1", "AC-0001 ", "OP-0001", "0001", "AC-00001"]
INEX_OP = ["OP-0099", "OP-9999", "op-0001", "OP-1", "AC-0001", "0001", "OP-0000"]
CUERPOS_RAW = ["", "{", "null", "[]", "{}", '{"m":1}', '{"m":null}', '{"m":""}', '{"M":"PING;1"}',
               '{"m":"PING;1","x":1}', '{"m":"PING;1","m":"PING;2"}', "  {\"m\":\"PING;1\"}  ", "PING;1"]
MONTO_RE = re.compile(r"[1-9][0-9]{0,9}")


class Generador:
    """Genera una secuencia con un modelo mínimo del estado, solo para elegir ids y montos con sentido."""

    def __init__(self, rng: random.Random):
        self.r = rng
        self.cuentas: list[tuple[str, str]] = []  # (id, titular)
        self.saldo: dict[str, int] = {}
        self.ops: list[str] = []
        self.pasos: list[dict] = []

    # ---- utilidades
    def add(self, m: str, tag: str):
        self.pasos.append({"t": "msg", "v": m, "tag": tag})

    def raw(self, cuerpo: str, tag: str):
        self.pasos.append({"t": "raw", "v": cuerpo, "tag": tag})

    def cuenta(self, inexistente_p=0.15) -> str:
        if not self.cuentas or self.r.random() < inexistente_p:
            return self.r.choice(INEX_CUENTA)
        return self.r.choice(self.cuentas)[0]

    def titular(self, id_: str):
        return next((t for i, t in self.cuentas if i == id_), None)

    def monto(self, origen: str | None = None) -> str:
        p = self.r.random()
        if p < 0.12:
            return self.r.choice(MONTOS_MAL)
        if origen in self.saldo and p < 0.35:
            return str(max(self.saldo[origen] + self.r.choice([-1, 0, 1]), 1))
        return self.r.choice(MONTOS_OK)

    def mal_control(self, cuerpo: str) -> str:
        e = esperado(cuerpo) or "1"
        variantes = [str((int(e) % 97) + 1), "0", "00", "97", "98", "002", "+" + e, " " + e, "x", e.zfill(3), "0" + e if len(e) == 1 else e + "0"]
        return f"{cuerpo};{self.r.choice(variantes)}"

    # ---- pasos individuales
    def alta(self, nombre=None, tag="alta"):
        nombre = nombre or self.r.choice(NOMBRES)
        self.add(firmar(f"ALTA;{nombre}"), tag)
        id_ = f"AC-{len(self.cuentas) + 1:04d}"
        self.cuentas.append((id_, nombre))
        self.saldo[id_] = 0

    def deposito(self, cuenta=None, monto=None, tag="deposito"):
        cuenta = cuenta or self.cuenta()
        monto = monto if monto is not None else self.monto(cuenta)
        self.add(firmar(f"DEPOSITO;{cuenta};{monto}"), tag)
        if cuenta in self.saldo and MONTO_RE.fullmatch(monto):
            self.saldo[cuenta] += int(monto)
            self.ops.append(f"OP-{len(self.ops) + 1:04d}")

    def transfer(self, o=None, d=None, monto=None, tag="transfer"):
        o = o or self.cuenta(0.1)
        d = d or (o if self.r.random() < 0.08 else self.cuenta(0.1))
        monto = monto if monto is not None else self.monto(o)
        self.add(firmar(f"TRANSFER;{o};{d};{monto}"), tag)
        if o in self.saldo and d in self.saldo and o != d and MONTO_RE.fullmatch(monto):
            m = int(monto)
            if m <= self.saldo[o] and (m <= 100000 or self.titular(o) == self.titular(d)):
                self.saldo[o] -= m
                self.saldo[d] += m
                self.ops.append(f"OP-{len(self.ops) + 1:04d}")

    def anula(self, op=None, tag="anula"):
        if op is None:
            op = self.r.choice(self.ops) if self.ops and self.r.random() < 0.8 else self.r.choice(INEX_OP)
        self.add(firmar(f"ANULA;{op}"), tag)

    def consulta(self, tag="consulta"):
        self.add(firmar(f"CONSULTA;{self.cuenta()}"), tag)

    def ping(self):
        self.add(self._ping(), "ping")

    def _ping(self) -> str:
        v = self.r.choice(["PING", "ping", "PING;x", "PING;64", "PING;a;b", "PiNg", "PING;1;2;3"])
        if v == "PING":
            return "PING;" + self.r.choice(["X", "64", "-1", "0", "999", "٦٤"])
        return firmar(v) if self.r.random() < 0.5 else v + ";" + self.r.choice(["X", "64", "1"])

    def notas(self):
        self.add(self.r.choice([firmar("NOTAS"), firmar("notas"), firmar("NOTAS;x"), "NOTAS;1", "NOTAS;"]), "notas")

    def halt(self):
        arg = self.r.choice(["1", "1", "a", "0", "01", "+1", " 1", "1 ", "2", "SI", "true"])
        self.add(self.r.choice([firmar(f"HALT;{arg}"), firmar(f"HALT;{arg}"), firmar("HALT"), firmar(f"HALT;{arg};x")]), "halt")

    def raro(self):
        """Formato/espacios/minúsculas/errores de control o de forma."""
        base = self.r.choice([
            f"CONSULTA;{self.cuenta(0.1)}", f"consulta;{self.cuenta(0.1)}", f" CONSULTA;{self.cuenta(0.1)}",
            f"CONSULTA ;{self.cuenta(0.1)}", f"CONSULTA;{self.cuenta(0.1)} ", f"CONSULTA;\t{self.cuenta(0.1)}",
            f"DEPOSITO;{self.cuenta()};{self.r.choice(MONTOS_OK)}", f"deposito;{self.cuenta()};{self.r.choice(MONTOS_OK)}",
            f"ALTA;{self.r.choice(NOMBRES)};{self.r.choice(NOMBRES)}", "ALTA", "ALTA;", ";", ";;", "A;", "XYZ;a;b;c",
            f"SALDOS;{self.cuenta()}", "HELP;1", "ANULAR;OP-0001", "CONSULTAR;AC-0001", "DEPOSIT;AC-0001;5", "TRANSFERIR;1;2;3",
            "PING;", "PING;;1", "ALTA;;x", "ÑÑ", "ÑANDÚ;x", "12345", "A", "ß;x", "TRANSFER;AC-0001;AC-0001;5",
            "RETIRA", "AYUDA", "ALTA;HD", "ALTA;KY", "ſALTA;x", "pıng", "ALTA;ß", "ALTA;ı;ſ", "x;٣", "AINA;1", "HANG;1",
            "HALTT;1", "NOTA;1", "NOTASS", "PIN", "CONSULTA;AC-0001;AC-0002", "DEPOSITO;AC-0001", "TRANSFER;AC-0001;AC-0002",
            "ANULA", "HALT;1;1", "ALTA;Ana;Perez;Lopez", "ÑALTA;x", "ALTA;日本",
        ])
        modo = self.r.random()
        if modo < 0.55 and ";" in base:
            self.add(firmar(base), "raro")
        elif modo < 0.8:
            self.add(self.mal_control(base), "control-malo")
        elif modo < 0.9 or ";" not in base:
            self.add(base, "sin-control")
        else:
            self.add(f"{base};{self.r.choice(['x', '002', '-1', '٢', '1.5'])}", "control-forma")

    def cuerpo_raw(self):
        if self.r.random() < 0.1:
            self.raw('{"m":"' + "A" * self.r.choice([8000, 8185, 8186, 9000]) + '"}', "cuerpo-grande")
        else:
            self.raw(self.r.choice(CUERPOS_RAW), "cuerpo-raw")

    # ---- macros
    def preparar(self):
        for _ in range(self.r.randint(1, 3)):
            self.alta(tag="preparar")
        if self.cuentas and self.r.random() < 0.8:
            self.deposito(self.cuentas[0][0], self.r.choice(["1000", "150000", "5000000", "5"]), "preparar")

    def macro_bloqueo(self):
        if len(self.cuentas) < 2:
            self.preparar()
        if len(self.cuentas) < 2:
            self.alta(tag="preparar")
            self.alta(tag="preparar")
        o, d = self.cuentas[0][0], self.cuentas[1][0]
        for _ in range(self.r.choice([2, 3, 3, 4])):
            self.transfer(o, d, self.r.choice(["100001", "999999999", str(self.saldo.get(o, 0) + 1 or 1)]), "bloqueo-fallo")
        self.transfer(o, d, "1", "bloqueo-valido")
        if self.r.random() < 0.5:
            self.deposito(self.r.choice([o, d]), "5", "bloqueo-deposito")
            self.transfer(o, d, "1", "bloqueo-tras-deposito")
        if self.r.random() < 0.3:
            self.transfer(d, o, "1", "bloqueo-recibe")

    def macro_anula(self):
        if not self.ops:
            self.preparar()
            self.deposito(self.cuentas[0][0], "1000") if self.cuentas else None
        op = self.r.choice(self.ops) if self.ops else "OP-0001"
        self.anula(op, "anula-1")
        self.anula(op, "anula-repetida")
        if self.cuentas:
            self.add(firmar(f"CONSULTA;{self.cuentas[0][0]}"), "anula-saldo")

    def macro_titular(self):
        nombre = self.r.choice(["Ana", "ana", "Beto"])
        self.alta(nombre, "titular")
        self.alta(self.r.choice([nombre, nombre, nombre.upper(), nombre + " "]), "titular")
        a, b = self.cuentas[-2][0], self.cuentas[-1][0]
        self.deposito(a, self.r.choice(["5000000", "10", "100000"]), "titular")
        self.transfer(a, b, self.r.choice(["120000", "2000000", "999999999", "100000", "100001"]), "titular-limite")

    def macro_contador(self):
        """Fallos, depósito en medio y nuevo fallo: ¿cuándo se bloquea?"""
        if len(self.cuentas) < 2:
            self.alta(tag="preparar")
            self.alta(tag="preparar")
        o, d = self.cuentas[-1][0], self.cuentas[0][0]
        for _ in range(self.r.choice([1, 2])):
            self.transfer(o, d, self.r.choice(["100001", "999999999"]), "contador-fallo")
        self.deposito(o, self.r.choice(["1", "100", "5"]), "contador-deposito")
        self.transfer(o, d, self.r.choice(["999999999", "100001"]), "contador-fallo")
        self.transfer(o, d, "1", "contador-valido")
        if self.r.random() < 0.5:
            self.transfer(o, d, "1", "contador-valido-2")

    def macro_combinado(self):
        c = self.cuenta(0.5)
        self.add(self.r.choice([
            firmar(f"XYZ;a;b;c;{c}"), firmar(f"DEPOSITO;{c};abc;extra"), firmar(f"DEPOSITO;AC-0099;{self.r.choice(MONTOS_MAL[:8])}"),
            firmar(f"TRANSFER;AC-0099;AC-0099;5"), firmar(f"TRANSFER;AC-0099;AC-0098;abc"), firmar(f"TRANSFER;{c};{c};abc"),
            firmar(f"TRANSFER;{c};{c};500000"), firmar(f"CONSULTA;{c};x"), firmar("ALTA;a;b"), firmar(f"ANULA;{c};x"),
            f"XYZ;{self.r.choice(['zz', '1', '99'])}", f"ALTA;{c};zz", f";x;{c}", f"ALTA;;{c};1",
            firmar(f"TRANSFER;{c};AC-0099;500000"), firmar(f"HALT;a;{c}"),
        ]), "combinado")

    def generar(self, n: int) -> list[dict]:
        if self.r.random() < 0.7:
            self.preparar()
        acciones = [
            (self.alta, 2), (self.deposito, 3), (self.transfer, 4), (self.consulta, 2), (self.anula, 2), (self.ping, 1),
            (self.notas, 1), (self.halt, 1), (self.raro, 3), (self.cuerpo_raw, 1), (self.macro_bloqueo, 1),
            (self.macro_anula, 1), (self.macro_titular, 1), (self.macro_contador, 1), (self.macro_combinado, 2),
        ]
        fs, ws = zip(*acciones)
        while len(self.pasos) < n:
            self.r.choices(fs, ws)[0]()
        return self.pasos[:n]


def secuencia(semilla: int, i: int) -> list[dict]:
    rng = random.Random(f"{semilla}/{i}")
    return Generador(rng).generar(rng.randint(2, 12))


def comando(paso: dict) -> str:
    return paso["v"].split(";")[0].upper()[:12] if paso["t"] == "msg" else "(cuerpo)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--desde", type=int, default=0)
    ap.add_argument("--max-requests", type=int, default=1000)
    ap.add_argument("--seguir", action="store_true", help="no parar en la primera diferencia de cada secuencia")
    ap.add_argument("--limpiar", action="store_true")
    a = ap.parse_args()

    SALIDA.mkdir(exist_ok=True)
    destino = SALIDA / "diferencias.jsonl"
    if a.limpiar and destino.exists():
        destino.unlink()
    local = Local()
    antes = usadas()
    grupos: Counter = Counter()
    ejemplos: dict = {}
    n_dif = n_ejecutadas = 0
    with cliente_original(max_requests=a.max_requests) as c, destino.open("a", encoding="utf-8") as salida:
        try:
            for i in range(a.desde, a.desde + a.n):
                pasos = secuencia(a.semilla, i)
                c.reset(f"diferencial semilla={a.semilla} seq={i}: estado inicial ({len(pasos)} pasos)")
                local.reset()
                historia: list[str] = []
                for j, p in enumerate(pasos):
                    hip = f"diferencial semilla={a.semilla} seq={i} paso={j} [{p['tag']}]: ¿el original responde igual que el reemplazo?"
                    if p["t"] == "msg":
                        e = c.msg(p["v"], hip)
                        s_l, r_l = local.msg_crudo(json.dumps({"m": p["v"]}, ensure_ascii=False))
                    else:
                        e = c.raw("POST", "/msg", hip, cuerpo_crudo=p["v"])
                        s_l, r_l = local.msg_crudo(p["v"])
                    historia.append(p["v"] if p["t"] == "msg" else "RAW:" + p["v"][:60])
                    if not iguales(e.status, e.response, s_l, r_l):
                        n_dif += 1
                        causa = f"{comando(p)} [{p['tag']}] original={resumen(e.status, e.response)} reemplazo={resumen(s_l, r_l)}"
                        grupos[causa] += 1
                        ejemplos.setdefault(causa, (a.semilla, i, j))
                        c.bitacora.concluir(e.id, f"DIFERENCIA con el reemplazo: {resumen(s_l, r_l)} (original {resumen(e.status, e.response)})")
                        salida.write(json.dumps({
                            "semilla": a.semilla, "secuencia": i, "paso": j, "tag": p["tag"], "log_id": e.id, "tipo": p["t"],
                            "request": p["v"] if p["t"] == "msg" else p["v"][:200], "historia": historia[:-1],
                            "original": {"status": e.status, "response": e.response},
                            "reemplazo": {"status": s_l, "response": r_l}, "causa": causa,
                        }, ensure_ascii=False) + "\n")
                        salida.flush()
                        if not a.seguir:
                            break
                n_ejecutadas += 1
        except Exception as error:  # incluye LimiteDeRequests
            print("PARADO:", type(error).__name__, error)
    print(f"semilla={a.semilla} secuencias ejecutadas={n_ejecutadas} requests={usadas() - antes} diferencias={n_dif}")
    for causa, k in grupos.most_common():
        print(f"  {k:3d} × {causa}   (ej.: semilla {ejemplos[causa][0]} seq {ejemplos[causa][1]} paso {ejemplos[causa][2]})")
    print(f"presupuesto usado en la tarea: {usadas()}/3000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
