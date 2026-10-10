"""Orden de evaluación de errores (anexo 2.5). Cada test indica la evidencia del log."""

import json

import pytest

from tests.conftest import TOKEN, codigo, cuenta


def codigo(r):
    j = r.json()
    return j.get("error") if isinstance(j, dict) else None


def cuenta(api, nombre="Ana"):
    r = api.msg(f"ALTA;{nombre}")
    assert r.status_code == 201
    return r.json()["cuentaId"]


# ---------------------------------------------------------------- nivel HTTP
def test_e404_antes_que_e001(client):
    # #111, #2558
    assert client.get("/nope").status_code == 404
    r = client.post("/health", content=b"{}")
    assert (r.status_code, r.json()["error"]) == (404, "E404")


def test_head_404_sin_cuerpo(client):
    # #30
    r = client.head("/health")
    assert r.status_code == 404 and r.content == b""


def test_e001_antes_que_e101_e100_e102(client):
    # #2547-#2549
    for cuerpo in (b'{"m": "' + b"A" * 20000, b"{", b"{}"):
        r = client.post("/msg", content=cuerpo)
        assert (r.status_code, r.json()["error"]) == (401, "E001")


@pytest.mark.parametrize("auth", ["Bearer falso", f"bearer {TOKEN}", TOKEN, "Bearer", f"Basic {TOKEN}", f"Bearer  {TOKEN}"])
def test_auth_variantes(client, auth):
    for ruta, metodo in (("/msg", "POST"), ("/health", "GET"), ("/__reset", "POST")):
        r = client.request(metodo, ruta, headers={"Authorization": auth})
        assert (r.status_code, r.json()) == (401, {"error": "E001", "mensaje": "no autorizado"})


def test_e101_antes_que_e100(api):
    # #2546: cuerpo enorme con JSON roto -> 413, no 400
    r = api.raw(b'{"m": "' + b"A" * 20000)
    assert (r.status_code, codigo(r)) == (413, "E101")


def test_umbral_8192(api):
    # #2132 / #2133
    def cuerpo_n(n):
        return ('{"m":"' + "A" * (n - 8) + '"}').encode()
    assert codigo(api.raw(cuerpo_n(8192))) == "E103"
    assert codigo(api.raw(cuerpo_n(8193))) == "E101"


def test_e100_e102_e103_e104(api):
    assert codigo(api.raw(b"")) == "E100"
    assert codigo(api.raw(b"PING;64")) == "E100"
    for c in (b"null", b"[]", b"{}", b'"PING;64"', b'{"m": 1}', b'{"m": null}', b'{"M": "PING;64"}'):
        assert codigo(api.raw(c)) == "E102", c
    assert codigo(api.msg_crudo("")) == "E103"
    assert codigo(api.msg_crudo("PING")) == "E103"
    for m in (";", "PING;", "PING;;64", "PING;64;", "ALTA;;x"):
        assert codigo(api.msg_crudo(m)) == "E104", m


def test_e104_antes_que_e201(api):
    assert codigo(api.msg_crudo("ALTA;;zz")) == "E104"  # #2556


def test_e201_antes_que_e301_y_e302(api):
    assert codigo(api.msg_crudo("XYZ;zz")) == "E201"  # #2553
    assert codigo(api.msg_crudo("ALTA;zz")) == "E201"  # #2554


def test_e202_antes_que_e301_y_e302(api):
    assert codigo(api.msg_crudo("XXXX;99")) == "E202"  # #284
    assert codigo(api.msg_crudo("ALTA;1")) == "E202"  # #2555


def test_e301_antes_que_e302_con_espacio_final_y_sugerencia(api):
    r = api.msg("XYZ;a;b;c;d")  # #2512
    assert codigo(r) == "E301"
    assert r.json() == {"error": "E301", "mensaje": "comando desconocido "}
    r = api.msg("HELP;1")
    assert r.json()["sugerencia"] == "HALT"  # #1507


def test_ping_no_valida_control_pero_si_segmentos_vacios(api):
    # #268-#278, #267
    for ctrl in ("X", "-1", "64.0", "0x40", "٦٤", "064", "640"):
        assert api.msg_crudo(f"PING;{ctrl}").json() == {"pong": True}
    assert codigo(api.msg_crudo("PING;")) == "E104"
    assert codigo(api.msg("PING;a")) == "E302"  # PING con argumentos


# ---------------------------------------------------------------- comandos
def test_e302_antes_que_e401_y_e303(api):
    assert codigo(api.msg("CONSULTA;AC-0099;extra")) == "E302"  # #2514
    assert codigo(api.msg("DEPOSITO;AC-0001;abc;x")) == "E302"  # #2519


def test_deposito_e303_antes_que_e401(api):
    assert codigo(api.msg("DEPOSITO;AC-0099;abc")) == "E303"  # #2516
    assert codigo(api.msg("DEPOSITO;AC-0099;5")) == "E401"


@pytest.mark.parametrize("monto,ok", [("1", True), ("9999999999", True), ("0", False), ("-5", False), ("1.5", False),
                                      ("007", False), ("+5", False), (" 5", False), ("٥", False), ("10000000000", False)])
def test_monto(api, monto, ok):
    a = cuenta(api)
    r = api.msg(f"DEPOSITO;{a};{monto}")
    assert (r.status_code == 200) == ok
    if not ok:
        assert codigo(r) == "E303"


def test_transfer_orden_de_errores(api):
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")
    assert codigo(api.msg(f"TRANSFER;{a};{a};abc")) == "E303"  # #2533: E303 antes que E304
    assert codigo(api.msg("TRANSFER;AC-0099;AC-0002;abc")) == "E303"  # #2535
    assert codigo(api.msg(f"TRANSFER;{a};{a};5")) == "E304"  # #1910
    assert codigo(api.msg(f"TRANSFER;{a};AC-0099;500000")) == "E401"  # #2529
    assert codigo(api.msg(f"TRANSFER;{a};{b};500000")) == "E506"  # E506 antes que E507: #2523
    assert codigo(api.msg(f"TRANSFER;{a};{b};1001")) == "E507"  # #2524
    assert api.msg(f"TRANSFER;{a};{b};1000").status_code == 200


def test_halt(api, client):
    # #1565, #1652, #1640-#1648
    assert codigo(api.msg("HALT;a")) == "E520"
    assert api.msg("PING").json() == {"pong": True}
    r = api.msg("HALT;1")
    assert (r.status_code, r.json()) == (503, {"error": "E599", "mensaje": "service halted"})
    for r in (api.raw(b"{"), api.raw(b"{}"), api.msg_crudo("ALTA;Ana;1"), api.raw(b'{"m":"' + b"A" * 9000 + b'"}'), api.msg("PING")):
        assert codigo(r) == "E599"
    assert client.get("/health", headers=api.auth).json() == {"ok": True}
    assert client.post("/nope").status_code == 404
    assert client.post("/msg", content=b"{}").status_code == 401
    assert api.reset().status_code == 200
    assert api.msg("PING").json() == {"pong": True}


def test_notas_estatica(api):
    r = api.msg("NOTAS")
    assert r.status_code == 200 and list(r.json()) == ["notas"] and r.json()["notas"][0]["id"] == "N-01"
    assert codigo(api.msg("NOTAS;x")) == "E302"


def test_perfil_alternativo_cambia_limite(api, monkeypatch):
    from app.config import reglas

    reglas.PERFILES["v_test"] = {"hereda": "v1", "limites": {"limite_transfer": 5}}
    try:
        monkeypatch.setenv("VERSION_REGLAS", "v_test")
        a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
        api.msg(f"DEPOSITO;{a};100")
        assert codigo(api.msg(f"TRANSFER;{a};{b};6")) == "E506"
    finally:
        del reglas.PERFILES["v_test"]
        reglas._cargar.cache_clear()


def test_captura_no_incluye_token(api, capsys):
    api.msg("PING")
    salida = capsys.readouterr().out
    assert "CAPTURA " in salida
    assert TOKEN not in salida and "Authorization" not in salida
    linea = [l for l in salida.splitlines() if l.startswith("CAPTURA ")][-1]
    d = json.loads(linea[len("CAPTURA "):])
    assert d["token_valido"] is True and d["status"] == 200 and d["metodo"] == "POST"

