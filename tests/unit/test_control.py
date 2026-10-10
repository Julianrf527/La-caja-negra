"""La fórmula del control contra pruebas/ejemplos.jsonl y las reglas del anexo (2.3)."""

import json
from pathlib import Path

import pytest

from app.config import reglas
from app.core import control

EJEMPLOS = [
    json.loads(l)
    for l in (Path(__file__).parents[2] / "test-original-app/pruebas/ejemplos.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
]


def _partes(m: str):
    cuerpo, _, ctrl = m.rpartition(";")
    return cuerpo, ctrl


@pytest.mark.parametrize("caso", [c for c in EJEMPLOS if not c["request"]["m"].upper().startswith("PING")], ids=lambda c: f"n{c['n']}")
def test_formula_contra_ejemplos(caso):
    cuerpo, ctrl = _partes(caso["request"]["m"])
    error = (caso["response"] or {}).get("error")
    if error == "E202":
        assert control.esperado(cuerpo) != ctrl
    elif error == "E201":
        assert not control.forma_valida(ctrl)
    else:
        assert control.forma_valida(ctrl)
        assert control.esperado(cuerpo) == ctrl


def test_ejemplo_conocido():
    assert control.esperado("CONSULTA;AC-0001") == "14"
    assert control.firmar("CONSULTA;AC-0001") == "CONSULTA;AC-0001;14"


def test_cero_se_codifica_como_97():
    assert control.esperado("AYUDA") == "97"  # (1 - 3N) mod 97 = 0 -> 97


def test_n_multiplo_de_97_tiene_control_98():  # #5076 (ÑÑ;98 pasa el control) y #5120-#5122
    assert control.esperado("RETIRA") == "98"
    assert control.esperado("ALTA;HD") == "98"
    assert control.esperado("ÑÑ") == "98"


def test_ignora_caracteres_que_no_son_letra_ni_digito_y_no_distingue_mayusculas():
    assert control.esperado("alta;ana maria") == control.esperado("ALTA;ANAMARIA")
    assert control.esperado("CONSULTa;AC-0001") == "14"


def test_cuerpo_largo_no_revienta():
    # N tendría ~16.000 dígitos; no debe lanzar (límite de int↔str de Python)
    assert control.esperado("A" * 8000) in map(str, range(2, 99))


@pytest.mark.parametrize("ctrl", ["2", "02", "97", "0", "00", "42"])
def test_forma_valida(ctrl):
    assert control.forma_valida(ctrl)


@pytest.mark.parametrize("ctrl", ["002", "+2", " 2", "2 ", "٢", "-2", "2.0", "0x2", "2a", "", "100", "2\n"])
def test_forma_invalida(ctrl):
    assert not control.forma_valida(ctrl)


def test_perfil_por_defecto_y_herencia():
    assert reglas.nombre_activo() == "v1"
    reglas.PERFILES["v_test"] = {"hereda": "v1", "limites": {"limite_transfer": 5}}
    try:
        p = reglas.resolver("v_test")
        assert p["limites"]["limite_transfer"] == 5
        assert p["limites"]["max_cuerpo_bytes"] == 8192  # heredado
        assert p["errores"]["E301"]["mensaje"] == "comando desconocido "
    finally:
        del reglas.PERFILES["v_test"]


def test_ejemplos_contra_la_app(api):
    """Los 20 ejemplos de la mañana, en orden, contra el reemplazo."""
    for caso in EJEMPLOS:
        r = api.msg_crudo(caso["request"]["m"])
        assert (r.status_code, r.json()) == (caso["status"], caso["response"]), f"n={caso['n']}"
