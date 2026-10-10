"""Dígito de control del protocolo: (1 - 3*N) mod 97, con N = cuerpo normalizado a entero."""


def _normalizar(cuerpo: str) -> int:
    partes = []
    for ch in cuerpo.upper():
        if "A" <= ch <= "Z":
            partes.append(str(ord(ch) - 64))
        elif ch in "0123456789":
            partes.append(ch)
    return int("".join(partes) or "0")


def control(cuerpo: str) -> int:
    # Rango 1..97: cuando (1 - 3N) mod 97 da 0, el servicio espera 97 (0 y 00 dan E202).
    return (1 - 3 * _normalizar(cuerpo)) % 97 or 97


def firmar(cuerpo: str) -> str:
    return f"{cuerpo};{control(cuerpo)}"
