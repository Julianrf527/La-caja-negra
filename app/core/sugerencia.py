"""Sugerencia del E301: comando interno más parecido (Levenshtein ≤ distancia configurada)."""


def levenshtein(a: str, b: str) -> int:
    previa = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        actual = [i]
        for j, y in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[-1] + 1, previa[j - 1] + (x != y)))
        previa = actual
    return previa[-1]


def sugerir(comando: str, candidatos, distancia_max: int) -> str | None:
    """`comando` ya en mayúsculas. Desempate: el primero de `candidatos` (supuesto)."""
    mejor, mejor_d = None, distancia_max + 1
    for c in candidatos:
        d = levenshtein(comando, c)
        if d < mejor_d:
            mejor, mejor_d = c, d
    return mejor
