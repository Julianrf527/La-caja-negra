"""Fase 2 de exploración: comandos, aridad/tipos, límites, memoria, precedencia de errores.

    python test-original-app/explorar_fase2.py <comandos|aridad|limites|memoria|precedencia|cambios>

Cada request pasa por Cliente (queda en el log) y lleva una hipótesis. Cada secuencia empieza con reset.
"""

import json
import sys
import time

from helper.cliente import Cliente, LimiteDeRequests
from helper.config import Config
from helper.control import firmar

PRESUPUESTO = {"notas2": 20, "notas": 60, "ocultos": 75, "duenos": 70, "repro": 70, "limite2": 90, "bloqueo3": 130, "bloqueo2": 130, "bloqueo": 220, "n0": 20, "barrido": 100, "halt2": 80, "halt": 60, "extra": 100, "comandos": 110, "aridad": 200, "limites": 330, "memoria": 130, "precedencia": 110, "cambios": 30}


def resumen(e) -> str:
    r = e.response
    if isinstance(r, dict) and "error" in r:
        extra = f" sugerencia={r['sugerencia']!r}" if "sugerencia" in r else ""
        return f"HTTP {e.status} {r['error']} {r.get('mensaje')!r}{extra}"
    return f"HTTP {e.status} {json.dumps(r, ensure_ascii=False)[:150]}"


class Lab:
    def __init__(self, c: Cliente):
        self.c = c

    def seq(self, motivo: str):
        return self.c.reset(f"reset: {motivo}")

    def m(self, cuerpo: str, hip: str, concl=None, firmado: bool = True):
        """Manda el cuerpo (firmado salvo firmado=False) y guarda la conclusión."""
        e = self.c.msg(firmar(cuerpo) if firmado else cuerpo, hip)
        texto = concl(e) if callable(concl) else concl
        self.c.bitacora.concluir(e.id, texto or resumen(e))
        return e

    def alta(self, nombre="Ana"):
        return self.m(f"ALTA;{nombre}", f"preparar: crear cuenta {nombre}")

    def dep(self, cuenta, monto, hip=None):
        return self.m(f"DEPOSITO;{cuenta};{monto}", hip or f"preparar: depositar {monto} en {cuenta}")

    def saldo(self, cuenta, hip=None):
        e = self.m(f"CONSULTA;{cuenta}", hip or f"leer saldo de {cuenta}")
        return e.response.get("saldo") if isinstance(e.response, dict) else None

    def base(self, saldo=1000):
        """reset + AC-0001 (saldo dado) + AC-0002 vacía."""
        self.seq("estado base: AC-0001 con saldo, AC-0002 vacía")
        self.alta("Ana")
        self.alta("Beto")
        if saldo:
            self.dep("AC-0001", saldo)


def umbral(lo, hi, ok):
    """lo cumple, hi no. Devuelve el mayor que cumple (asume monotonía)."""
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo


# ---------------------------------------------------------------------------
def comandos(L: Lab):
    L.seq("buscar comandos ocultos; un comando existente da E302 (aridad) y uno inexistente E301")
    nombres = (
        "SALDO SALDOS BAJA RETIRO RETIRA RETIRAR HISTORIAL MOVIMIENTOS LISTA LISTAR ESTADO CIERRE HELP AYUDA VERSION "
        "ECHO REVERSA REVERSAR BLOQUEA CONGELA EXTRACTO TITULAR CUENTA OPERACION INFO STATUS TIME RESET ADMIN DEBUG "
        "STATS MODIFICA BORRA PAGO COBRO TRANSFERENCIA DEPOSITAR CONSULTAR ANULAR CANCELA REVERTIR CONFIRMA"
    ).split()
    for n in nombres:
        L.m(n, f"¿existe el comando {n}? (E302 = existe, E301 = no)")
    L.seq("sugerencias del E301 con errores de tipeo")
    tipeos = ["PIN", "PNG", "PINGG", "ALT", "ALTAA", "CONSULT", "CONSULTAA", "DEPOSIT", "DEPOSITOO", "TRANSFE",
              "TRANSFERR", "ANUL", "ANULAA", "XYZ", "ZZZZZZZZZZ", "ping2", "PING2", "CONSULTO", "DEPOSITE", "TRANSFER2", "ANULO"]
    for t in tipeos:
        L.m(f"{t};AC-0001", f"E301 para {t}: ¿trae sugerencia y cuál?")
    L.m("PING ;1", "comando con espacio final: ¿desconocido con sugerencia PING?")
    L.m("PING\t;1", "comando con tabulador final")
    L.m("ÑANDÚ;1", "comando con caracteres no ASCII (el control los ignora)")


def aridad(L: Lab):
    # PING
    L.base()
    for b, h in [("PING;a;b;c", "PING con muchos argumentos"), ("PING;", None)]:
        if h:
            L.m(b, f"{h}: ¿acepta cualquier aridad?")
    # ALTA
    L.base()
    casos = {
        "ALTA": "ALTA sin argumentos (aridad)",
        "ALTA;Ana": "ALTA con nombre repetido: ¿crea otra cuenta o rechaza duplicado?",
        "ALTA;Ana;Perez": "ALTA con 2 args (aridad, ya visto con Lucia;Gomez)",
        "ALTA;a;b;c": "ALTA con 3 args",
        "ALTA;123": "ALTA con nombre numérico",
        "ALTA;ana maria": "ALTA con espacio en el nombre",
        "ALTA;Ñandú": "ALTA con acentos/ñ",
        "ALTA;" + "A" * 300: "ALTA con nombre de 300 caracteres",
        "ALTA;AC-0001": "ALTA con nombre con forma de id de cuenta",
        "ALTA;a-b_c.d": "ALTA con signos en el nombre",
        "ALTA;ana": "ALTA nombre en minúsculas",
        "ALTA;ANA": "ALTA nombre en mayúsculas",
    }
    for b, h in casos.items():
        L.m(b, h)
    L.m("CONSULTA;AC-0005", "tras las altas anteriores, ¿qué cuentas existen? (último id asignado)")
    # CONSULTA
    L.base()
    casos = {
        "CONSULTA": "CONSULTA sin args", "CONSULTA;AC-0001;AC-0002": "CONSULTA con 2 args",
        "CONSULTA;ac-0001": "id de cuenta en minúsculas", "CONSULTA;AC-1": "id sin ceros",
        "CONSULTA;AC-00001": "id con 5 dígitos", "CONSULTA;AC-0001x": "id con basura al final",
        "CONSULTA; AC-0001": "id con espacio inicial", "CONSULTA;OP-0001": "prefijo OP en CONSULTA",
        "CONSULTA;0001": "id sin prefijo", "CONSULTA;AC-0000": "AC-0000", "CONSULTA;AC-9999": "AC-9999 inexistente",
        "CONSULTA;AC--1": "id negativo", "CONSULTA;AC-": "id sin número", "CONSULTA;AC-0002": "cuenta vacía: saldo 0",
        "CONSULTA;AC-0001 ": "id con espacio final",
    }
    for b, h in casos.items():
        L.m(b, h)
    # DEPOSITO
    L.base()
    casos = {
        "DEPOSITO": "DEPOSITO sin args", "DEPOSITO;AC-0001": "DEPOSITO con 1 arg", "DEPOSITO;AC-0001;5;6": "DEPOSITO con 3 args",
        "DEPOSITO;AC-0099;5": "DEPOSITO a cuenta inexistente", "DEPOSITO;AC-0001;0": "monto 0",
        "DEPOSITO;AC-0001;-5": "monto negativo", "DEPOSITO;AC-0001;1.5": "monto decimal",
        "DEPOSITO;AC-0001;1,5": "monto con coma", "DEPOSITO;AC-0001;abc": "monto no numérico",
        "DEPOSITO;AC-0001;1e3": "monto notación científica", "DEPOSITO;AC-0001;007": "monto con ceros a la izquierda",
        "DEPOSITO;AC-0001;+5": "monto con +", "DEPOSITO;AC-0001; 5": "monto con espacio inicial",
        "DEPOSITO;AC-0001;5 ": "monto con espacio final", "DEPOSITO;AC-0001;٥": "monto con dígito árabe",
        "DEPOSITO;AC-0001;0x10": "monto hexadecimal", "DEPOSITO;AC-0001;1_000": "monto con guion bajo",
        "DEPOSITO;ac-0001;5": "cuenta en minúsculas", "DEPOSITO;OP-0001;5": "prefijo OP como cuenta",
        "DEPOSITO;AC-0001;1": "monto mínimo 1",
    }
    for b, h in casos.items():
        L.m(b, h)
    L.saldo("AC-0001", "saldo tras los depósitos válidos: ¿cuáles montos se aplicaron?")
    # TRANSFER
    L.base()
    casos = {
        "TRANSFER": "TRANSFER sin args", "TRANSFER;AC-0001;AC-0002": "TRANSFER con 2 args",
        "TRANSFER;AC-0001;AC-0002;5;6": "TRANSFER con 4 args", "TRANSFER;AC-0001;AC-0001;5": "origen = destino",
        "TRANSFER;AC-0099;AC-0002;5": "origen inexistente", "TRANSFER;AC-0001;AC-0099;5": "destino inexistente",
        "TRANSFER;AC-0098;AC-0099;5": "ambas inexistentes: ¿cuál se reporta?", "TRANSFER;AC-0001;AC-0002;0": "monto 0",
        "TRANSFER;AC-0001;AC-0002;-5": "monto negativo", "TRANSFER;AC-0001;AC-0002;1.5": "monto decimal",
        "TRANSFER;AC-0001;AC-0002;abc": "monto no numérico", "TRANSFER;AC-0001;AC-0002;007": "monto con ceros",
        "TRANSFER;ac-0001;ac-0002;5": "ids en minúsculas", "TRANSFER;AC-0001;AC-0002;1": "monto 1 válido",
        "TRANSFER;AC-0002;AC-0001;2": "transferir desde cuenta con saldo 1 (insuficiente)",
        "TRANSFER;AC-0001;OP-0001;5": "destino con prefijo OP",
    }
    for b, h in casos.items():
        L.m(b, h)
    # ANULA
    L.base()
    L.m("TRANSFER;AC-0001;AC-0002;100", "preparar: transferencia OP-0002 para anular")
    casos = {
        "ANULA": "ANULA sin args", "ANULA;OP-0002;OP-0001": "ANULA con 2 args", "ANULA;OP-9999": "ANULA op inexistente",
        "ANULA;AC-0001": "ANULA con id de cuenta", "ANULA;op-0002": "op en minúsculas", "ANULA;OP-2": "op sin ceros",
        "ANULA;0002": "op sin prefijo", "ANULA;OP-0000": "OP-0000", "ANULA;OP-0001": "anular el depósito OP-0001",
        "ANULA;OP-0002": "anular la transferencia OP-0002",
    }
    for b, h in casos.items():
        L.m(b, h)


def limites(L: Lab):
    c = L.c
    # --- límite de DEPOSITO ---
    L.base(saldo=0)
    ok_prev = 1
    fallo = None
    k = 6
    while k <= 22:
        monto = 10**k
        e = L.dep("AC-0001", monto, f"¿DEPOSITO tiene tope? probar 10^{k}")
        if e.status != 200:
            fallo = monto
            break
        ok_prev = monto
        k += 2
    if fallo is None:
        L.m("CONSULTA;AC-0001", "saldo tras depósitos enormes: ¿se guarda exacto?", None)
    else:
        top = umbral(ok_prev, fallo, lambda x: L.dep("AC-0001", x, f"búsqueda binaria del tope de DEPOSITO: {x}").status == 200)
        c.bitacora.concluir(c.bitacora.leer()[-1].id, f"tope de DEPOSITO por request = {top} (el siguiente falla)")
    for monto in (2**31 - 1, 2**31, 2**53, 2**53 + 1, 2**63 - 1, 2**63, 2**64):
        L.dep("AC-0001", monto, f"¿enteros especiales en DEPOSITO? {monto}")
    L.saldo("AC-0001", "saldo tras depósitos grandes")

    # --- depósitos repetidos: ¿límite acumulado/contador? ---
    L.base(saldo=0)
    for i in range(15):
        L.dep("AC-0001", 100000, f"depósito repetido #{i+1} de 100000: ¿tope acumulado o por número de operaciones?")
    L.saldo("AC-0001", "saldo tras 15 depósitos de 100000 (esperado 1500000)")

    # --- límite de TRANSFER (E506) ---
    def buscar_limite(saldo, hip_base, destino_previo=0):
        L.base(saldo=0)
        L.dep("AC-0001", saldo, f"{hip_base}: saldo origen {saldo}")
        if destino_previo:
            L.dep("AC-0002", destino_previo, f"{hip_base}: destino con saldo {destino_previo}")

        def ok(x):
            e = L.m(f"TRANSFER;AC-0001;AC-0002;{x}", f"{hip_base}: ¿pasa transferir {x}?")
            if e.status == 200:
                L.dep("AC-0001", x, f"{hip_base}: restaurar saldo origen tras transferir {x}")
                return True
            return False

        return ok

    ok = buscar_limite(210000, "límite TRANSFER con saldo 210000")
    assert ok(100000)
    ultimo_ok = umbral(100000, 120000, ok) if not ok(120000) else None
    texto = f"con saldo origen 210000, el mayor TRANSFER aceptado es {ultimo_ok}" if ultimo_ok else "120000 pasó con saldo 210000 (cambió la regla)"
    c.bitacora.concluir(c.bitacora.leer()[-1].id, texto)

    ok = buscar_limite(10_000_000, "límite TRANSFER con saldo 10.000.000")
    if ok(120000):
        for x in (200000, 500000, 1_000_000, 5_000_000, 10_000_000):
            if not ok(x):
                break
    else:
        ult = umbral(1, 120000, ok)
        c.bitacora.concluir(c.bitacora.leer()[-1].id, f"con saldo 10M el mayor TRANSFER aceptado es {ult}")

    ok = buscar_limite(210000, "límite TRANSFER con saldo 210000 y destino con 5.000.000", destino_previo=5_000_000)
    ok(100000)
    ok(110000)
    ok(120000)

    # acumulado: repetir 100000 varias veces
    L.base(saldo=0)
    L.dep("AC-0001", 5_000_000, "preparar: saldo 5M para acumulado de transferencias")
    for i in range(10):
        L.m("TRANSFER;AC-0001;AC-0002;100000", f"transferencia repetida #{i+1} de 100000: ¿tope acumulado?")
    L.saldo("AC-0001", "saldo origen tras 10 transferencias (esperado 4.000.000)")

    # --- número de cuentas ---
    L.seq("¿hay máximo de cuentas y cómo crece el id?")
    for i in range(1, 36):
        L.m(f"ALTA;U{i}", f"alta #{i}: ¿cambia el formato del id o hay tope?")

    # --- tamaño del cuerpo (E101) ---
    L.seq("umbral exacto del E101 por tamaño de cuerpo")

    def cuerpo_n(n):  # n bytes totales
        return '{"m":"' + "A" * (n - 8) + '"}'

    def pasa(n):
        e = c.raw("POST", "/msg", f"umbral de cuerpo: {n} bytes", cuerpo_crudo=cuerpo_n(n))
        c.bitacora.concluir(e.id, resumen(e))
        return e.status != 413

    top = umbral(1000, 10000, pasa)
    c.bitacora.concluir(c.bitacora.leer()[-1].id, f"el mayor cuerpo que no da 413 es {top} bytes totales (JSON incluido)")
    for n in (top, top + 1):
        e = c.raw("POST", "/msg", f"borde del E101: {n} bytes", cuerpo_crudo=cuerpo_n(n))
        c.bitacora.concluir(e.id, resumen(e))


def memoria(L: Lab):
    # ANULA y saldos
    L.base(saldo=0)
    L.dep("AC-0001", 1000, "preparar OP-0001 depósito 1000")
    L.m("TRANSFER;AC-0001;AC-0002;300", "preparar OP-0002 transferencia 300")
    L.saldo("AC-0001", "saldos antes de anular: origen")
    L.saldo("AC-0002", "saldos antes de anular: destino")
    L.m("ANULA;OP-0002", "ANULA de transferencia: ¿devuelve el dinero a origen y lo quita al destino?")
    L.saldo("AC-0001", "origen tras ANULA de la transferencia (700 si no revierte, 1000 si revierte)")
    L.saldo("AC-0002", "destino tras ANULA de la transferencia (300 si no revierte, 0 si revierte)")
    L.m("ANULA;OP-0002", "anular otra vez la misma operación")
    L.m("ANULA;OP-0001", "ANULA del depósito: ¿quita 1000 del saldo?")
    L.saldo("AC-0001", "origen tras ANULA del depósito")
    L.dep("AC-0001", 5, "depósito tras ANULA: ¿qué OP id recibe? (¿ANULA consume contador?)")

    # ANULA que dejaría saldo negativo
    L.base(saldo=1000)
    L.m("TRANSFER;AC-0001;AC-0002;900", "preparar: mover 900 a AC-0002 (OP-0002)")
    L.m("ANULA;OP-0001", "anular el depósito cuando el dinero ya se movió: ¿saldo negativo, error o ok?")
    L.saldo("AC-0001", "saldo del origen tras anular depósito sin fondos")
    L.m("ANULA;OP-0002", "anular la transferencia cuando el origen ya quedó en 100-1000...")
    L.saldo("AC-0001", "origen final")
    L.saldo("AC-0002", "destino final")
    # anular transferencia cuando el destino ya gastó
    L.base(saldo=1000)
    L.m("TRANSFER;AC-0001;AC-0002;500", "preparar: AC-0002 recibe 500 (OP-0002)")
    L.m("TRANSFER;AC-0002;AC-0001;400", "AC-0002 devuelve 400 (OP-0003)")
    L.m("ANULA;OP-0002", "anular transferencia cuando el destino ya gastó parte: ¿falla por saldo del destino?")
    L.saldo("AC-0001", "origen final")
    L.saldo("AC-0002", "destino final")

    # contadores con errores
    L.seq("contadores AC- y OP- cuando hay errores")
    L.m("ALTA;Ana", "primera alta: AC-0001")
    L.m("ALTA;Ana;X", "ALTA con error de aridad: ¿consume id?")
    L.m("ALTA;Ana", "alta siguiente: ¿AC-0002 (no se consumió) o AC-0003?", firmado=True)
    L.m("ALTA;Zoe", "alta tras errores", None)
    e = L.m("ALTA;Bad", "ALTA con control inválido: ¿consume id?", firmado=False) if False else None
    bad = firmar("ALTA;Bad").rsplit(";", 1)
    L.m(f"{bad[0]};{(int(bad[1]) + 1) % 97}", "ALTA con control inválido (E202): ¿consume id?", firmado=False)
    L.m("ALTA;Final", "alta tras control inválido: ¿qué id recibe?")
    L.dep("AC-0099", 10, "DEPOSITO a cuenta inexistente: ¿consume OP?")
    L.dep("AC-0001", "abc", "DEPOSITO con monto inválido: ¿consume OP?")
    L.dep("AC-0001", 10, "primer depósito válido: ¿OP-0001?")
    L.m("TRANSFER;AC-0001;AC-0002;999999999", "TRANSFER con saldo insuficiente/ límite: ¿consume OP?")
    L.m("TRANSFER;AC-0001;AC-0099;1", "TRANSFER a cuenta inexistente: ¿consume OP?")
    L.m("TRANSFER;AC-0001;AC-0001;1", "TRANSFER a la misma cuenta: ¿consume OP?")
    L.m("TRANSFER;AC-0001;AC-0002;1", "primera transferencia válida: ¿OP-0002 o salta números?")
    L.m("ANULA;OP-0009", "ANULA inexistente: ¿consume OP?")
    L.m("ANULA;OP-0002", "ANULA válida: ¿consume OP?")
    L.dep("AC-0001", 1, "depósito siguiente: confirma cuántos OP se consumieron")
    L.m("CONSULTA;AC-0001", "CONSULTA no consume OP/AC")
    L.m("PING;1", "PING no consume")
    L.dep("AC-0001", 1, "depósito final: confirma contador tras consultas y ping")

    # ¿los depósitos son inmediatos?
    L.base(saldo=0)
    L.dep("AC-0001", 777, "depósito: status 'recieved'")
    L.saldo("AC-0001", "saldo inmediato (¿ya incluye 777?)")
    time.sleep(5)
    L.saldo("AC-0001", "saldo 5 s después (¿cambia con el tiempo?)")

    # reset
    L.seq("tras el reset los contadores vuelven")
    L.m("ALTA;Ana", "tras reset: ¿AC-0001 otra vez?")
    L.dep("AC-0001", 1, "tras reset: ¿OP-0001 otra vez?")
    L.m("ANULA;OP-0001", "tras reset: ANULA OP-0001")
    L.m("ANULA;OP-0001", "reanular tras reset")


def precedencia(L: Lab):
    L.base(saldo=1000)
    pruebas = [
        ("XYZ;a;b;c;d", "comando desconocido + muchos args: ¿E301 antes que E302?"),
        ("XYZ", "comando desconocido sin args"),
        ("CONSULTA;AC-0099;extra", "aridad mala + cuenta inexistente: ¿E302 o E401?"),
        ("CONSULTA;xx", "id mal formado en CONSULTA: ¿E401 o formato?"),
        ("DEPOSITO;AC-0099;abc", "cuenta inexistente + monto inválido: ¿cuál gana?"),
        ("DEPOSITO;AC-0099;-5", "cuenta inexistente + monto negativo"),
        ("DEPOSITO;AC-0099;0", "cuenta inexistente + monto 0"),
        ("DEPOSITO;AC-0001;abc;x", "aridad + monto inválido"),
        ("TRANSFER;AC-0098;AC-0099;5", "origen y destino inexistentes"),
        ("TRANSFER;AC-0098;AC-0001;5", "origen inexistente, destino ok"),
        ("TRANSFER;AC-0001;AC-0099;5", "destino inexistente, origen ok"),
        ("TRANSFER;AC-0001;AC-0002;500000", "monto > límite y > saldo: ¿E506 o E507?"),
        ("TRANSFER;AC-0001;AC-0002;1001", "monto > saldo pero < límite: E507"),
        ("TRANSFER;AC-0001;AC-0099;500000", "destino inexistente + sobre límite + sin saldo"),
        ("TRANSFER;AC-0099;AC-0002;500000", "origen inexistente + sobre límite + sin saldo"),
        ("TRANSFER;AC-0001;AC-0001;500000", "misma cuenta + sobre límite"),
        ("TRANSFER;AC-0001;AC-0001;5", "misma cuenta con monto válido"),
        ("TRANSFER;AC-0001;AC-0001;abc", "misma cuenta + monto inválido"),
        ("TRANSFER;AC-0001;AC-0002;abc", "monto inválido, cuentas ok"),
        ("TRANSFER;AC-0099;AC-0002;abc", "origen inexistente + monto inválido"),
        ("TRANSFER;AC-0001;AC-0002;0", "monto 0, cuentas ok"),
        ("TRANSFER;AC-0001;AC-0002;-500000", "monto negativo grande"),
        ("TRANSFER;AC-0002;AC-0001;5", "origen sin saldo, destino ok, monto pequeño"),
        ("TRANSFER;AC-0002;AC-0099;5", "origen sin saldo + destino inexistente"),
        ("ANULA;OP-9999;x", "aridad + op inexistente"),
        ("ANULA;xx", "ANULA con formato no válido"),
        ("ALTA;;x", "segmento vacío en medio + control válido (E104)"),
        ("CONSULTA;;", "varios segmentos vacíos"),
        ("ALTA;Ana;;", "aridad + vacíos"),
    ]
    fallos = 0
    for b, h in pruebas:
        if b.startswith("TRANSFER") and fallos >= 2:  # evitar el bloqueo E510 (3 fallos 422 seguidos)
            L.base(saldo=1000)
            fallos = 0
        e = L.m(b, h)
        fallos = fallos + 1 if e.status == 422 else fallos
    # cuerpo: errores simultáneos de nivel HTTP / formato (sin firmar)
    c = L.c
    L.seq("precedencia entre errores de nivel 'cuerpo'")
    grande_roto = '{"m": "' + "A" * 20000
    c.raw("POST", "/msg", "cuerpo enorme y JSON roto: ¿E101 o E100?", cuerpo_crudo=grande_roto)
    c.raw("POST", "/msg", "cuerpo enorme, sin token: ¿E001 o E101?", cuerpo_crudo=grande_roto, auth=None)
    c.raw("POST", "/msg", "JSON roto sin token: ¿E001 o E100?", cuerpo_crudo="{", auth=None)
    c.raw("POST", "/msg", "sin m y sin token: ¿E001 o E102?", cuerpo_crudo="{}", auth=None)
    c.raw("POST", "/msg", "m con solo ';': E104 o E103", cuerpo={"m": ";;"})
    c.raw("POST", "/msg", "m sin ';' pero con espacios: E103", cuerpo={"m": "ALTA Ana"})
    c.raw("POST", "/msg", "m = 'A;'  → segmento vacío vs control", cuerpo={"m": "A;"})
    c.raw("POST", "/msg", "m con control no numérico y comando desconocido: E201 antes que E301", cuerpo={"m": "XYZ;zz"})
    c.raw("POST", "/msg", "m con control no numérico y aridad mala: E201 vs E302", cuerpo={"m": "ALTA;zz"})
    c.raw("POST", "/msg", "m con control inválido y aridad mala: E202 vs E302", cuerpo={"m": "ALTA;1"})
    c.raw("POST", "/msg", "control con segmento vacío antes: E104 vs E201", cuerpo={"m": "ALTA;;zz"})
    c.raw("POST", "/msg", "m con salto de línea y control", cuerpo={"m": "ALTA;Ana\n;5"})
    c.raw("POST", "/health", "POST /health sin token: ¿401 o 404?", cuerpo_crudo="{}", auth=None)
    c.raw("GET", "/nope", "GET ruta inexistente con body", cuerpo_crudo="{}", auth=None)
    c.raw("GET", "/msg", "GET /msg sin token", auth=None)
    c.raw("DELETE", "/health", "DELETE /health sin token", auth=None)


def cambios(L: Lab):
    c = L.c
    casos = [json.loads(l) for l in open("test-original-app/pruebas/ejemplos.jsonl", encoding="utf-8") if l.strip()]
    L.seq("re-ejecutar ejemplos.jsonl para detectar cambios del servicio durante el día")
    dif = 0
    for caso in casos:
        e = c.raw("POST", "/msg", f"ejemplo {caso['n']}: ¿sigue igual que en la mañana?", cuerpo=caso["request"])
        igual = (e.status, e.response) == (caso["status"], caso["response"])
        dif += not igual
        c.bitacora.concluir(e.id, "igual que ejemplos.jsonl" if igual else f"DIFERENTE: {resumen(e)} (esperado {caso['status']} {caso['response']})")
    print(f"cambios: {dif} diferencias de {len(casos)}")


def extra(L: Lab):
    L.seq("comando oculto sugerido (HALT) y control 0")
    for n in ("HALT", "halt", "HALT;1", "HALT;AC-0001", "HALT;a;b"):
        L.m(n, f"¿existe HALT (sugerido por el servidor en E301 de HELP)? probar {n!r}")
    # control cuyo valor correcto es 0: ¿cómo se acepta?
    for forma in ("0", "00", "97", "000", "-0"):
        L.m(f"AYUDA;{forma}", f"AYUDA cuyo control calculado es 0: ¿acepta la forma {forma!r}?", firmado=False)
    L.m("AYUDA;0", "control calculado 0 escrito como '0'", firmado=False)
    L.m("ALTA;" + "X", "control normal para comparar con el caso 0")
    # buscar otros comandos ocultos por vecindad (sugerencia != comando conocido)
    palabras = ("STOP QUIT EXIT KILL HALTA HOLD HALF HELD HEAL HELM HALO SHUTDOWN CRASH SLEEP WAIT RESTART BOOM TEST FAIL ERROR "
                "ERR LOCK OPEN CLOSE FLUSH SYNC DUMP LOAD SAVE PURGE CLEAR WIPE SET GET PUT POST LIST LS DEL ADD SUB MUL DIV "
                "SEND PAY BUY SELL FEE TAX INTERES COMISION BONO PREMIO MULTA CUOTA CREDITO DEBITO ABONO CARGO PRESTAMO "
                "ALTAS BAJAS BAJA CONSULTAS ANULAS").split()
    for p in palabras:
        L.m(f"{p};1", f"vecindad: ¿{p} existe o sugiere un comando oculto?")


def halt(L: Lab):
    c = L.c
    e = c.health("tras HALT: ¿/health sigue respondiendo?")
    c.bitacora.concluir(e.id, resumen(e))
    L.m("PING;1", "tras HALT: ¿PING responde?")
    L.m("CONSULTA;AC-0001", "tras HALT: ¿cualquier comando da E599?")
    e = c.raw("POST", "/nope", "tras HALT: ruta inexistente", cuerpo_crudo="{}")
    c.bitacora.concluir(e.id, resumen(e))
    e = c.raw("POST", "/msg", "tras HALT: JSON roto (¿E100 o E599?)", cuerpo_crudo="{")
    c.bitacora.concluir(e.id, resumen(e))
    e = c.raw("POST", "/msg", "tras HALT: sin m (¿E102 o E599?)", cuerpo_crudo="{}")
    c.bitacora.concluir(e.id, resumen(e))
    L.m("ALTA;Ana;1", "tras HALT: control inválido (¿E202 o E599?)", firmado=False)
    e = c.raw("POST", "/msg", "tras HALT: sin token", cuerpo={"m": "PING;1"}, auth=None)
    c.bitacora.concluir(e.id, resumen(e))
    e = L.seq("el reset debe sacar al servicio del estado halted")
    c.bitacora.concluir(e.id, resumen(e))
    L.m("PING;1", "tras reset: ¿PING vuelve a responder?")
    L.m("ALTA;Ana", "tras reset: ¿el estado de cuentas quedó limpio?")
    for cuerpo, hip in (("HALT;71", "HALT sin argumentos reales (solo control): E302"),
                        ("HALT;a", "HALT con 1 arg: ¿detiene?")):
        L.m(cuerpo, hip, firmado=(cuerpo != "HALT;71"))
    L.m("PING;1", "tras HALT;a: ¿quedó halted?")
    L.seq("reset tras halt de 1 arg")
    L.m("HALT;a;b", "HALT con 2 args: ¿aridad o halt?")
    L.m("PING;1", "tras HALT;a;b: ¿halted?")
    L.seq("reset tras halt de 2 args")
    L.m("HALT;a;b;c", "HALT con 3 args")
    L.m("PING;1", "tras HALT 3 args")
    L.seq("reset")
    # control = 0
    for forma in ("0", "00", "97", "000"):
        L.m(f"AYUDA;{forma}", f"AYUDA cuyo control calculado es 0: ¿acepta la forma {forma!r}?", firmado=False)
    L.m("RETIRA;0", "RETIRA con control 0 (calculado 0): E202 de nuevo?", firmado=False)
    L.m("RETIRA;97", "RETIRA con 97", firmado=False)
    L.m("ALTA;X;0", "ALTA con control 0 donde el calculado no es 0", firmado=False)


def halt2(L: Lab):
    for conf in ("1", "0", "SI", "YES", "TRUE", "CONFIRMA", "OK", "Y", "si", "yes", "CONFIRM", "2", "true", "S"):
        L.seq(f"antes de probar la confirmación {conf!r} de HALT")
        e = L.m(f"HALT;{conf}", f"HALT con confirmación {conf!r}: ¿detiene (E599 después) o pide confirmar (E520)?")
        e2 = L.m("PING", f"tras HALT;{conf}: ¿PING responde pong o E599?")
    L.seq("controles con formas distintas, comando conocido (CONSULTA;AC-0005 → 2)")
    for forma in ("2", "02", "002", "+2", " 2", "2 ", "2.0", "-2", "٢", "0x2", "2a"):
        L.m(f"CONSULTA;AC-0005;{forma}", f"forma del control {forma!r} cuando el valor correcto es 2", firmado=False)
    L.m("ALTA;Ana;97", "control 97 donde el calculado no es 97 (¿comodín?)", firmado=False)
    L.m("ALTA;Ana;98", "control 98 (fuera de 0..97)", firmado=False)
    L.m("ALTA;Ana;99", "control 99", firmado=False)
    L.m("ALTA;Ana;100", "control 100", firmado=False)
    L.m("AYUDA", "control calculado 0 ahora firmado como 97")
    L.m("RETIRA", "otro cuerpo cuyo control calculado es 0, firmado como 97")


def barrido(L: Lab):
    L.seq("cuerpo RETIRA (N múltiplo de 97): la fórmula predice 1 y el servidor lo rechaza; barrer controles")
    for k in range(2, 97):
        e = L.m(f"RETIRA;{k}", f"barrido de control para RETIRA (N=185209181, múltiplo de 97): ¿{k} es aceptado?", firmado=False)
        if not (isinstance(e.response, dict) and e.response.get("error") == "E202"):
            L.c.bitacora.concluir(e.id, f"control aceptado para RETIRA = {k}: {resumen(e)}")
            break


def n0(L: Lab):
    L.seq("cuerpos con N múltiplo de 97: ¿existe algún control válido?")
    cuerpos = ['ALTA;HD', 'ALTA;KY', 'ALTA;LV', 'ALTA;MS', 'ALTA;NP']
    for cu in cuerpos[:3]:
        for k in ("1", "97", "0", "2"):
            L.m(f"{cu};{k}", f"N múltiplo de 97 en {cu!r}: ¿se acepta el control {k}? (fórmula predice 1)", firmado=False)


def bloqueo(L: Lab):
    c = L.c

    def base3():
        L.base(saldo=1_000_000)
        L.alta("Cata")

    # A: cuántos fallos E506 seguidos hasta E510 y qué queda bloqueado
    base3()
    for i in range(1, 7):
        L.m("TRANSFER;AC-0001;AC-0002;120000", f"fallo E506 #{i} seguido en la misma cuenta origen: ¿cuándo aparece E510 'cuenta bloqueada'?")
    L.m("TRANSFER;AC-0001;AC-0002;1", "origen bloqueado: transferencia válida pequeña")
    L.m("TRANSFER;AC-0002;AC-0001;1", "destino bloqueado (AC-0002 sin saldo): ¿bloquea al que recibe?")
    L.m("TRANSFER;AC-0003;AC-0002;1", "otra cuenta (AC-0003, sin saldo) no bloqueada: ¿E507 normal?")
    L.m("DEPOSITO;AC-0001;5", "cuenta bloqueada: ¿acepta DEPOSITO?")
    L.m("CONSULTA;AC-0001", "cuenta bloqueada: ¿acepta CONSULTA?")
    L.m("ANULA;OP-0001", "cuenta bloqueada: ¿acepta ANULA de su depósito?")
    L.m("TRANSFER;AC-0001;AC-0002;0", "bloqueada + monto inválido: ¿E510 o E303?")
    L.m("TRANSFER;AC-0001;AC-0099;1", "bloqueada + destino inexistente: ¿E510 o E401?")
    L.m("TRANSFER;AC-0001;AC-0001;1", "bloqueada + misma cuenta: ¿E510 o E304?")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "bloqueada + sobre límite: ¿E510 o E506?")
    L.m("TRANSFER;AC-0099;AC-0002;1", "origen inexistente no tiene bloqueo: E401")
    time.sleep(20)
    L.m("TRANSFER;AC-0001;AC-0002;1", "bloqueo tras 20 s: ¿se levanta con el tiempo?")
    time.sleep(45)
    L.m("TRANSFER;AC-0001;AC-0002;1", "bloqueo tras 65 s: ¿se levanta con el tiempo?")
    L.seq("el reset levanta el bloqueo")
    L.alta("Ana"); L.alta("Beto"); L.dep("AC-0001", 1000)
    L.m("TRANSFER;AC-0001;AC-0002;1", "tras reset: transferencia normal")

    # B: qué errores cuentan para el bloqueo
    for etiqueta, cuerpo in (
        ("E507 saldo insuficiente", "TRANSFER;AC-0002;AC-0001;5"),
        ("E401 destino inexistente", "TRANSFER;AC-0001;AC-0099;5"),
        ("E303 monto inválido", "TRANSFER;AC-0001;AC-0002;abc"),
        ("E304 origen=destino", "TRANSFER;AC-0001;AC-0001;5"),
        ("E302 aridad", "TRANSFER;AC-0001;AC-0002"),
        ("E202 control inválido", None),
    ):
        base3()
        origen = "AC-0002" if "E507" in etiqueta else "AC-0001"
        for i in range(1, 6):
            if cuerpo is None:
                L.m("TRANSFER;AC-0001;AC-0002;5;1", f"{etiqueta} #{i}: ¿cuenta para el bloqueo?", firmado=False)
            else:
                L.m(cuerpo, f"{etiqueta} #{i} seguido: ¿cuenta para el bloqueo de {origen}?")
        L.m("TRANSFER;AC-0001;AC-0002;1" if origen == "AC-0001" else "TRANSFER;AC-0002;AC-0003;0", f"tras 5x {etiqueta}: ¿{origen} sigue operando?")
        if origen == "AC-0002":
            L.m("TRANSFER;AC-0002;AC-0001;5", "AC-0002 tras 5 E507: ¿E510 ahora?")

    # C: un éxito reinicia el contador
    base3()
    for i in range(1, 4):
        L.m("TRANSFER;AC-0001;AC-0002;120000", f"E506 #{i} (2 antes del éxito)" if i < 3 else "E506 #3 tras éxito intermedio")
        if i == 2:
            L.m("TRANSFER;AC-0001;AC-0002;5", "éxito entre fallos: ¿reinicia el contador?")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "E506 #4 (contando el 3º tras el éxito)")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "E506 #5")
    # fallos intercalados con otros comandos (CONSULTA) y fallos en otra cuenta
    base3()
    L.m("TRANSFER;AC-0001;AC-0002;120000", "fallo 1 (AC-0001)")
    L.m("TRANSFER;AC-0003;AC-0002;120000", "fallo E507/E506 en AC-0003 (¿contador global?)")
    L.m("CONSULTA;AC-0001", "consulta entre fallos")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "fallo 2 (AC-0001)")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "fallo 3 (AC-0001)")
    L.m("TRANSFER;AC-0001;AC-0002;1", "tras 3 fallos de AC-0001 con ruido: ¿bloqueada?")
    L.m("TRANSFER;AC-0003;AC-0002;1", "AC-0003 con 1 fallo: ¿bloqueada?")
    # E506 con otros orígenes y exactamente por monto
    base3()
    L.dep("AC-0003", 1_000_000)
    for i in range(1, 5):
        L.m("TRANSFER;AC-0003;AC-0001;120000", f"E506 #{i} desde AC-0003 (otra cuenta): ¿se bloquea igual tras 3?")
    L.m("TRANSFER;AC-0001;AC-0002;1", "AC-0001 no ha fallado: debe operar")


def bloqueo2(L: Lab):
    c = L.c

    def bloquear(tag):
        L.base(saldo=1_000_000)
        for i in range(3):
            L.m("TRANSFER;AC-0001;AC-0002;120000", f"{tag}: fallo E506 #{i+1} para bloquear AC-0001")
        return time.monotonic()

    # (a) duración del bloqueo: sondear cada ~1 s con una transferencia válida
    t0 = bloquear("duración del bloqueo")
    desbloqueo = None
    for i in range(30):
        time.sleep(0.6)
        e = L.m("TRANSFER;AC-0001;AC-0002;1", f"sondeo #{i+1} a {time.monotonic()-t0:.1f}s del bloqueo: ¿sigue bloqueada?")
        if e.status == 200:
            desbloqueo = time.monotonic() - t0
            c.bitacora.concluir(e.id, f"primera transferencia aceptada ~{desbloqueo:.1f}s después del 3er fallo (sondeando cada ~1s)")
            break
    # (b) sin sondear: ¿los intentos E510 extienden el bloqueo?
    if desbloqueo:
        t0 = bloquear("bloqueo sin sondeos intermedios")
        time.sleep(max(desbloqueo - 2.5, 0))
        e = L.m("TRANSFER;AC-0001;AC-0002;1", f"único sondeo a ~{desbloqueo-2.5:.1f}s: ¿sigue bloqueada?")
        time.sleep(4)
        L.m("TRANSFER;AC-0001;AC-0002;1", "sondeo 4 s después")
    # (c) mezcla E506/E507 cuenta para el bloqueo
    L.base(saldo=1000)
    L.m("TRANSFER;AC-0001;AC-0002;120000", "mezcla: E506 (1)")
    L.m("TRANSFER;AC-0001;AC-0002;5000", "mezcla: E507 (2)")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "mezcla: E506 (3)")
    L.m("TRANSFER;AC-0001;AC-0002;5", "mezcla: ¿bloqueada tras E506+E507+E506?")
    # (d) umbral exacto con 2 fallos
    L.base(saldo=1000)
    L.m("TRANSFER;AC-0001;AC-0002;5000", "dos E507 seguidos (1)")
    L.m("TRANSFER;AC-0001;AC-0002;5000", "dos E507 seguidos (2)")
    L.m("TRANSFER;AC-0001;AC-0002;5", "tras 2 fallos: ¿opera?")
    # (e) E510 vs E507: cuenta bloqueada sin saldo
    L.base(saldo=0)
    for i in range(3):
        L.m("TRANSFER;AC-0001;AC-0002;5", f"E507 #{i+1} desde cuenta vacía")
    L.m("TRANSFER;AC-0001;AC-0002;5", "bloqueada y sin saldo: E510 o E507")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "bloqueada, sobre límite y sin saldo: E506 antes de E510")
    # (f) ¿ANULA de una transferencia con origen bloqueado?
    L.base(saldo=1000)
    L.m("TRANSFER;AC-0001;AC-0002;10", "OP-0002 para anular con origen bloqueado")
    for i in range(3):
        L.m("TRANSFER;AC-0001;AC-0002;5000", f"E507 #{i+1} para bloquear")
    L.m("ANULA;OP-0002", "ANULA de transferencia cuyo origen está bloqueado")
    # (g) el bloqueo del destino no impide recibir
    L.m("TRANSFER;AC-0002;AC-0001;1", "destino bloqueado recibe: AC-0002 envía a AC-0001 (AC-0001 bloqueada)")
    L.m("DEPOSITO;AC-0001;1", "depósito a bloqueada")


def bloqueo3(L: Lab):
    def bloquear(tag):
        L.base(saldo=1_000_000)
        for i in range(3):
            L.m("TRANSFER;AC-0001;AC-0002;120000", f"{tag}: E506 #{i+1} para bloquear AC-0001")
        L.m("TRANSFER;AC-0001;AC-0002;1", f"{tag}: confirmar bloqueo (E510 esperado)")

    for espera in (8, 15, 30):
        bloquear(f"espera {espera}s")
        time.sleep(espera)
        L.m("TRANSFER;AC-0001;AC-0002;1", f"¿el bloqueo expira solo tras {espera}s sin requests?")
    for nombre, cuerpo in (("DEPOSITO a la cuenta bloqueada", "DEPOSITO;AC-0001;5"), ("CONSULTA de la cuenta bloqueada", "CONSULTA;AC-0001"),
                           ("ANULA del depósito OP-0001", "ANULA;OP-0001"), ("DEPOSITO a otra cuenta", "DEPOSITO;AC-0002;5"),
                           ("PING", "PING"), ("ALTA", "ALTA;Zeta"), ("CONSULTA de otra cuenta", "CONSULTA;AC-0002")):
        bloquear(f"limpiar con {nombre}")
        L.m(cuerpo, f"¿{nombre} levanta el bloqueo?")
        L.m("TRANSFER;AC-0001;AC-0002;1", f"tras {nombre}: ¿sigue bloqueada?")
    # orden entre E510, E506, E507 con el bloqueo ya activo
    bloquear("orden E510/E506")
    L.m("TRANSFER;AC-0001;AC-0002;120000", "bloqueada + sobre límite con saldo suficiente: ¿E510 o E506?")
    L.m("TRANSFER;AC-0001;AC-0002;5000000", "bloqueada + sobre límite + sin saldo: ¿E510 o E506/E507?")
    L.m("TRANSFER;AC-0001;AC-0099;1", "bloqueada + destino inexistente (E401 antes?)")
    L.m("TRANSFER;AC-0099;AC-0001;1", "origen inexistente, destino bloqueado")


def limite2(L: Lab):
    for saldo in (10, 1000, 200000):
        for monto in (100001, 500000, 999999999, 1000000000, 9999999999):
            L.base(saldo=saldo)
            L.m(f"TRANSFER;AC-0001;AC-0002;{monto}", f"saldo {saldo}, monto {monto}: ¿E506 (límite) o E507 (saldo)? (memoria vio E507 con 999999999)")


def repro(L: Lab):
    big = "TRANSFER;AC-0001;AC-0002;999999999"
    # 1) misma secuencia de memoria, recortada: ¿se reproduce E507?
    L.seq("repro: secuencia de memoria que dio E507 para 999999999")
    L.m("ALTA;Ana", "repro: alta 1")
    L.m("ALTA;Ana;X", "repro: ALTA aridad")
    L.m("ALTA;Ana", "repro: alta 2")
    L.m("ALTA;Zoe", "repro: alta 3")
    L.dep("AC-0099", 10, "repro: depósito a inexistente")
    L.dep("AC-0001", "abc", "repro: monto inválido")
    L.dep("AC-0001", 10, "repro: depósito 10")
    L.m(big, "repro: TRANSFER 999999999 con saldo 10 (¿E507 otra vez?)")
    L.m(big, "repro: mismo TRANSFER otra vez (¿cambia?)")
    # 2) mínimo: solo saldo 10 y dos cuentas
    L.base(saldo=10)
    L.m(big, "mínimo: saldo 10, 2 cuentas, 999999999")
    # 3) con 3 cuentas
    L.seq("repro: mismas cuentas, cada variación por separado")
    L.alta("Ana"); L.alta("Ana"); L.dep("AC-0001", 10)
    L.m(big, "repro: AC-0002 existe (2 altas), saldo 10")
    L.seq("repro: un depósito fallido antes")
    L.alta("Ana"); L.alta("Beto"); L.dep("AC-0001", "abc"); L.dep("AC-0001", 10)
    L.m(big, "repro: tras DEPOSITO inválido (E303)")
    L.seq("repro: un depósito a cuenta inexistente antes")
    L.alta("Ana"); L.alta("Beto"); L.dep("AC-0099", 10); L.dep("AC-0001", 10)
    L.m(big, "repro: tras DEPOSITO a inexistente (E401)")
    L.seq("repro: un E202 antes")
    L.alta("Ana"); L.alta("Beto"); L.m("ALTA;Bad;1", "repro: control inválido", firmado=False); L.dep("AC-0001", 10)
    L.m(big, "repro: tras E202")
    L.seq("repro: ALTA con aridad mala antes")
    L.alta("Ana"); L.alta("Beto"); L.m("ALTA;Ana;X", "repro: aridad"); L.dep("AC-0001", 10)
    L.m(big, "repro: tras E302")


def duenos(L: Lab):
    for a, b in (("Ana", "Ana"), ("Beto", "Beto"), ("Ana", "ana"), ("Ana", "ANA"), ("Ana", "Anb"), ("Ana", "Ana Maria"), ("Ana", "Beto"), ("123", "123")):
        L.seq(f"límite de TRANSFER con titulares {a!r} -> {b!r}")
        L.alta(a)
        L.alta(b)
        L.dep("AC-0001", 5_000_000)
        L.m("TRANSFER;AC-0001;AC-0002;120000", f"titulares {a!r}->{b!r}: ¿se aplica el límite de 100000 (E506) o el mismo titular lo evita?")
        L.m("TRANSFER;AC-0001;AC-0002;2000000", f"titulares {a!r}->{b!r}: monto 2.000.000 con saldo 5.000.000")
    # mismo titular: saldo insuficiente con monto grande
    L.seq("mismo titular, saldo insuficiente")
    L.alta("Ana"); L.alta("Ana"); L.dep("AC-0001", 10)
    L.m("TRANSFER;AC-0001;AC-0002;120000", "mismo titular, saldo 10, monto 120000: ¿E507?")
    L.m("TRANSFER;AC-0001;AC-0002;999999999", "mismo titular, saldo 10, monto 999999999")
    # ¿el titular se compara por nombre o por cuenta? tres cuentas con mismo nombre
    L.seq("tres cuentas 'Ana'")
    L.alta("Ana"); L.alta("Ana"); L.alta("Ana"); L.dep("AC-0001", 5_000_000)
    L.m("TRANSFER;AC-0001;AC-0003;120000", "AC-0001 -> AC-0003 mismo nombre")
    L.m("TRANSFER;AC-0003;AC-0002;120000", "AC-0003 -> AC-0002 mismo nombre")


def ocultos(L: Lab):
    L.seq("segunda búsqueda de comandos ocultos (E302 = existe, E301 = no)")
    nombres = ("RESETEA REINICIA APAGA DETEN PARA CIERRA BORRAR ELIMINA CONGELAR BLOQUEAR DESBLOQUEA DESBLOQUEAR UNLOCK FREEZE LIMITE LIMITES "
               "CONFIG CONFIGURA SET_LIMITE MODO DUMP LOG LOGS TRACE METRICAS SALUD HEALTH PONG HOLA HI HELLO WHOAMI QUIEN TOKEN CLAVE "
               "CAMBIA RENOMBRA TITULARES CUENTAS OPERACIONES ULTIMA ULTIMO CUENTA_ID TOTAL SUMA PROMEDIO CONTAR COUNT").split()
    for n in nombres:
        L.m(n, f"¿existe el comando {n}? (E302 = existe, E301 = no)")
    # ¿el halt tiene prioridad sobre E101 (cuerpo grande)?
    L.seq("HALT y errores de cuerpo")
    L.m("HALT;1", "HALT con confirmación '1': detiene el servicio")
    e = L.c.raw("POST", "/msg", "tras HALT: cuerpo grande (¿E101 o E599?)", cuerpo_crudo='{"m":"' + "A" * 9000 + '"}')
    L.c.bitacora.concluir(e.id, resumen(e))
    e = L.c.raw("GET", "/health", "tras HALT: /health")
    L.c.bitacora.concluir(e.id, resumen(e))
    L.seq("reset tras HALT")


def notas(L: Lab):
    L.base(saldo=1000)
    for n in ("NOTAS", "NOTA", "NOTAR", "NOTE", "MEMO", "COMENTA", "APUNTE", "ETIQUETA", "TAG", "TOTALES", "TOTALS"):
        L.m(n, f"{n} sin args: ¿existe (E302) o sugiere NOTAS (E301)?")
    for cuerpo, hip in (
        ("NOTAS;hola", "NOTAS con 1 arg: ¿qué hace?"),
        ("NOTAS;AC-0001", "NOTAS con una cuenta"),
        ("NOTAS;AC-0001;hola", "NOTAS cuenta + texto"),
        ("NOTAS;AC-0001;hola;mundo", "NOTAS con 3 args"),
        ("NOTAS;OP-0001", "NOTAS con una operación"),
        ("NOTAS;OP-0001;hola", "NOTAS operación + texto"),
        ("NOTAS;AC-0099;hola", "NOTAS cuenta inexistente"),
        ("NOTAS;OP-0099;hola", "NOTAS operación inexistente"),
        ("NOTAS;hola;mundo", "NOTAS 2 args que no son ids"),
    ):
        L.m(cuerpo, hip)
    L.m("CONSULTA;AC-0001", "CONSULTA tras NOTAS: ¿cambió el cuerpo de respuesta (campo notas)?")
    L.m("NOTAS;AC-0001", "NOTAS de nuevo: ¿lista lo guardado?")
    L.m("DEPOSITO;AC-0001;5", "DEPOSITO tras NOTAS: ¿el contador OP avanza igual?")


def notas2(L: Lab):
    L.seq("NOTAS justo después del reset")
    L.m("NOTAS", "NOTAS sin actividad previa")
    L.alta("Ana"); L.dep("AC-0001", 5); L.m("TRANSFER;AC-0001;AC-0001;1", "error E304 de relleno")
    L.m("NOTAS", "NOTAS tras actividad y un error: ¿la lista cambia?")
    L.m("notas", "NOTAS en minúsculas")
    L.m("NOTAS;x", "NOTAS con 1 arg: aridad")


FASES = {f.__name__: f for f in (notas2, notas, ocultos, duenos, repro, limite2, bloqueo3, bloqueo2, bloqueo, n0, barrido, halt2, halt, extra, comandos, aridad, limites, memoria, precedencia, cambios)}

if __name__ == "__main__":
    fase = sys.argv[1]
    with Cliente(Config(), max_requests=PRESUPUESTO[fase]) as c:
        try:
            FASES[fase](Lab(c))
            print(f"{fase}: ok, {c.enviados} requests")
        except LimiteDeRequests as error:
            print(f"{fase}: se alcanzó el tope ({error})")
