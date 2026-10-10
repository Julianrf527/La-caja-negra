"""Estado en memoria: contadores, bloqueo E510, titulares, ANULA y reset (anexo 5)."""

from tests.conftest import codigo, cuenta


def test_bloqueo_e510_antes_que_e506_y_e507(api):
    # #2139-#2142, #2440, #2441, #2322, #2323, #2442
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000000")
    for _ in range(3):
        assert codigo(api.msg(f"TRANSFER;{a};{b};120000")) == "E506"
    assert codigo(api.msg(f"TRANSFER;{a};{b};1")) == "E510"
    assert codigo(api.msg(f"TRANSFER;{a};{b};120000")) == "E510"
    assert codigo(api.msg(f"TRANSFER;{a};{b};5000000")) == "E510"
    assert codigo(api.msg(f"TRANSFER;{a};{b};0")) == "E303"
    assert codigo(api.msg(f"TRANSFER;{a};{a};1")) == "E304"
    assert codigo(api.msg(f"TRANSFER;{a};AC-0099;1")) == "E401"
    # CONSULTA, ANULA y depósito a otra cuenta no desbloquean; un depósito a la propia, sí (#2370)
    assert api.msg(f"CONSULTA;{a}").status_code == 200
    assert codigo(api.msg(f"TRANSFER;{a};{b};1")) == "E510"
    assert api.msg(f"DEPOSITO;{b};5").status_code == 200
    assert codigo(api.msg(f"TRANSFER;{a};{b};1")) == "E510"
    assert api.msg(f"DEPOSITO;{a};5").status_code == 200
    assert api.msg(f"TRANSFER;{a};{b};1").status_code == 200


def test_dos_fallos_no_bloquean_y_un_exito_reinicia(api):
    # #2313-#2315, #2235-#2240
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000000")
    for _ in range(2):
        api.msg(f"TRANSFER;{a};{b};120000")
    assert api.msg(f"TRANSFER;{a};{b};5").status_code == 200
    for _ in range(2):
        assert codigo(api.msg(f"TRANSFER;{a};{b};120000")) == "E506"
    assert api.msg(f"TRANSFER;{a};{b};5").status_code == 200


def test_otros_errores_no_cuentan_para_el_bloqueo(api):
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")
    for cuerpo in (f"TRANSFER;{a};AC-0099;5", f"TRANSFER;{a};{b};abc", f"TRANSFER;{a};{a};5", f"TRANSFER;{a};{b}"):
        for _ in range(5):
            api.msg(cuerpo)
    assert api.msg(f"TRANSFER;{a};{b};5").status_code == 200


def test_mismo_titular_sin_limite_y_distinto_con_limite(api):
    # #2706-#2762
    for t1, t2, ok in (("Ana", "Ana", True), ("Ana", "ana", False), ("Ana", "Beto", False)):
        api.reset()
        a, b = cuenta(api, t1), cuenta(api, t2)
        api.msg(f"DEPOSITO;{a};5000000")
        r = api.msg(f"TRANSFER;{a};{b};2000000")
        assert (r.status_code == 200) == ok, (t1, t2)
        if not ok:
            assert codigo(r) == "E506"
    api.reset()
    a, b = cuenta(api, "Ana"), cuenta(api, "Ana")
    api.msg(f"DEPOSITO;{a};10")
    assert codigo(api.msg(f"TRANSFER;{a};{b};999999999")) == "E507"  # #2677


def test_anula_revierte_sin_validar_fondos(api):
    # #2448-#2476
    a, b = cuenta(api, "Ana"), cuenta(api, "Beto")
    api.msg(f"DEPOSITO;{a};1000")  # OP-0001
    api.msg(f"TRANSFER;{a};{b};900")  # OP-0002
    assert api.msg("ANULA;OP-0001").json() == {"ok": True, "anulada": "OP-0001"}
    assert api.msg(f"CONSULTA;{a}").json()["saldo"] == -900
    assert api.msg("ANULA;OP-0001").json() == {"ok": False, "motivo": "ya anulada"}
    assert api.msg("ANULA;OP-0002").json()["ok"] is True
    assert api.msg(f"CONSULTA;{a}").json()["saldo"] == 0
    assert api.msg(f"CONSULTA;{b}").json()["saldo"] == 0
    for ident in ("OP-9999", "AC-0001", "op-0002", "OP-2", "0002", "OP-0000"):
        assert codigo(api.msg(f"ANULA;{ident}")) == "E402"
    # ANULA no consume contador de operaciones
    assert api.msg(f"DEPOSITO;{a};1").json()["operacionId"] == "OP-0003"


def test_contadores_no_avanzan_con_errores(api):
    api.msg("ALTA;Ana")
    api.msg("ALTA;Ana;X")
    assert api.msg("ALTA;Ana").json() == {"cuentaId": "AC-0002"}  # #2478-#2483
    api.msg("DEPOSITO;AC-0099;10")
    api.msg("DEPOSITO;AC-0001;abc")
    assert api.msg("DEPOSITO;AC-0001;10").json() == {"status": "recieved", "operacionId": "OP-0001"}


def test_reset_repone_contadores(api):
    api.msg("ALTA;Ana")
    api.reset()
    assert api.msg("ALTA;Ana").json() == {"cuentaId": "AC-0001"}
