import json
from pathlib import Path

from app.config import reglas
from app.core.sugerencia import levenshtein, sugerir

LOG = Path(__file__).parents[2] / "test-original-app/experimentos.jsonl"


def test_levenshtein():
    assert levenshtein("HELP", "HALT") == 2
    assert levenshtein("PIN", "PING") == 1
    assert levenshtein("", "ABC") == 3


def test_sugerencias_del_log():
    perfil = reglas.activo()
    candidatos = sorted(perfil["comandos"])  # desempate alfabético confirmado (#3797-#3811)
    n = 0
    for linea in LOG.read_text(encoding="utf-8").splitlines():
        e = json.loads(linea)
        r = e["response"]
        if isinstance(r, dict) and r.get("error") == "E301" and isinstance(e["request"], dict):
            cmd = e["request"]["m"].split(";")[0].upper()
            assert sugerir(cmd, candidatos, perfil["limites"]["distancia_sugerencia"]) == r.get("sugerencia"), e["id"]
            n += 1
    assert n >= 100
