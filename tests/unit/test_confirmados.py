"""Puntos antes «pendientes de confirmar», ya comprobados contra el original (ids del log entre paréntesis)."""

import pytest

from tests.conftest import codigo, cuenta


def _bloquear(api, origen, destino):
    """Tres E507 seguidos desde `origen` (sin saldo) y comprobación de E510."""
    for _ in range(3):
        assert codigo(api.msg(f"TRANSFER;{origen};{destino};5")) == "E507"
    assert codigo(api.msg(f"TRANSFER;{origen};{destino};5")) == "E510"


def test_cuenta_bloqueada_puede_recibir(api):  # #3695-#3703
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")
    _bloquear(api, b, a)
    assert api.msg(f"TRANSFER;{a};{b};5").status_code == 200
    assert api.msg(f"CONSULTA;{b}").json()["saldo"] == 5


def test_deposito_que_desbloquea_reinicia_el_contador(api):  # #3705-#3714
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")
    _bloquear(api, b, a)
    assert api.msg(f"DEPOSITO;{b};1").status_code == 200
    assert codigo(api.msg(f"TRANSFER;{b};{a};5")) == "E507"
    assert api.msg(f"TRANSFER;{b};{a};1").status_code == 200


def test_cualquier_deposito_reinicia_el_contador_aunque_no_este_bloqueada(api):  # #3716-#3723
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")
    for _ in range(2):
        assert codigo(api.msg(f"TRANSFER;{b};{a};5")) == "E507"
    assert api.msg(f"DEPOSITO;{b};100").status_code == 200
    assert codigo(api.msg(f"TRANSFER;{b};{a};500")) == "E507"
    assert api.msg(f"TRANSFER;{b};{a};1").status_code == 200  # no está bloqueada: el contador se reinició


def test_tras_desbloquear_hacen_falta_tres_fallos_para_bloquear_de_nuevo(api):  # #3725-#3736
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")
    _bloquear(api, b, a)
    api.msg(f"DEPOSITO;{b};1")
    for _ in range(3):
        assert codigo(api.msg(f"TRANSFER;{b};{a};5")) == "E507"
    assert codigo(api.msg(f"TRANSFER;{b};{a};1")) == "E510"


def test_e507_entre_mismo_titular_cuenta_para_el_bloqueo(api):  # #3738-#3744
    a, b = cuenta(api, "Ana"), cuenta(api, "Ana")
    api.msg(f"DEPOSITO;{a};10")
    for _ in range(3):
        assert codigo(api.msg(f"TRANSFER;{a};{b};999999999")) == "E507"
    assert codigo(api.msg(f"TRANSFER;{a};{b};1")) == "E510"


def test_e304_gana_a_e401_con_la_misma_cuenta_inexistente(api):  # #3746-#3748
    assert codigo(api.msg("TRANSFER;AC-0099;AC-0099;5")) == "E304"
    assert codigo(api.msg("TRANSFER;AC-0099;AC-0099;abc")) == "E303"


@pytest.mark.parametrize("arg", ["01", "+1", " 1", "1 ", "1.0", "１"])
def test_halt_solo_acepta_la_confirmacion_exacta(api, arg):  # #3750-#3766
    assert codigo(api.msg(f"HALT;{arg}")) == "E520"
    assert api.msg("PING").json() == {"pong": True}


def test_ping_con_argumentos_no_valida_el_control(api):  # #3768-#3771
    assert codigo(api.msg_crudo("PING;a;X")) == "E302"
    assert codigo(api.msg_crudo("PING;a;b;X")) == "E302"
    assert codigo(api.msg_crudo("PING;a;")) == "E104"


@pytest.mark.parametrize("m,esperado", [
    ("ß;x;21", "E202"),   # control calculado con ß→SS: el original lo rechaza (#3773)
    ("ß;x;26", "E301"),   # ß se ignora en el control (#3774)
    ("ß;ß;x;73", "E202"),  # #3775
    ("conſulta;AC-0001;14", "E202"),  # ſ no se convierte en S (#3777)
    ("pıng;64", "E202"),  # ı no se convierte en I: no es PING y el control no cuadra (#3781)
    ("x;٣;26", "E301"),   # los dígitos no ASCII no cuentan (#3785)
    ("ÑÑ;1", "E202"), ("-;97", "E202"), ("-;0", "E202"), ("-;50", "E202"),  # N = 0: ningún control (#3789-#3795)
])
def test_unicode_no_se_normaliza(api, m, esperado):
    assert codigo(api.msg_crudo(m)) == esperado


@pytest.mark.parametrize("palabra,esperada", [
    ("AINA", "ALTA"), ("HANG", "HALT"), ("AAT", "ALTA"), ("ANA", "ALTA"),
    ("NTA", "ALTA"), ("AALA", "ALTA"), ("HNLA", "ANULA"), ("NOLA", "ANULA"),
])
def test_empate_de_sugerencia_elige_el_primero_alfabetico(api, palabra, esperada):  # #3797-#3811
    assert api.msg(f"{palabra};AC-0001").json()["sugerencia"] == esperada


@pytest.mark.parametrize("cuerpo,esperado", [
    (b'{"m":"PING;1","x":NaN}', "E100"),          # #4618: el original rechaza NaN
    (b'{"m":"PING;1","x":-Infinity}', "E100"),
    (b'{"m":"PING;64","n":1e999}', None),          # #4637: 1e999 sí se acepta (pong)
    (b'{"m":"PING;64",}', "E100"),                 # #4619
    (b"{'m':'PING;64'}", "E100"),                  # #4620
    (b'{"m":"PING;64"} x', "E100"),                # #4621
    (b'{"m":"PING;64"}\n\n', None),                # #4622
    (b'\xef\xbb\xbf{"m":"PING;64"}', "E100"),        # #4623: BOM
    (b'{"m":"PING\\u003b64"}', None),              # #4624: escape unicode
    (b'{"m":"PING;64","m":1}', "E102"),            # #4625: gana la última clave
    (b"1", "E102"), (b"true", "E102"),             # #4635-#4636
])
def test_json_bordes(api, cuerpo, esperado):
    r = api.raw(cuerpo)
    assert codigo(r) == esperado
    if esperado is None:
        assert r.json() == {"pong": True}


@pytest.mark.parametrize("d,esperado", [(20, "E102"), (21, "E100"), (100, "E100"), (3000, "E100")])  # #4640-#4647
def test_profundidad_de_listas(api, d, esperado):
    assert codigo(api.raw("[" * d + "]" * d)) == esperado


@pytest.mark.parametrize("n,esperado", [(19, None), (20, "E100")])  # #4649-#4654: el objeto raíz cuenta como un nivel
def test_profundidad_con_objeto_raiz(api, n, esperado):
    assert codigo(api.raw('{"m":"PING;64","a":' + "[" * n + "]" * n + "}")) == esperado
    assert codigo(api.raw('{"m":"PING;64","a":' + '{"a":' * n + "1" + "}" * n + "}")) == (esperado if n == 20 else None)
