"""Dígito de control (ISO 7064 MOD 97-10): esperado = 98 − (3·N mod 97), con N construido del cuerpo."""

import re

from app.config import reglas


_A_MAYUSCULAS = {ord(c): c.upper() for c in "abcdefghijklmnopqrstuvwxyz"}


def mayusculas_ascii(texto: str) -> str:
    """Pasa a mayúsculas solo a-z. El original no normaliza caracteres especiales:
    'ß', 'ſ' y 'ı' no se convierten en SS, S ni I (confirmado: #3773-#3783)."""
    return texto.translate(_A_MAYUSCULAS)


def _n_modulo(cuerpo: str, modulo: int) -> int:
    """N mod `modulo`, sin construir el entero (los cuerpos largos exceden el límite de int↔str).

    Cada letra A–Z aporta los dígitos de su posición (A=1…Z=26); cada dígito 0–9 se queda igual;
    el resto de caracteres se ignora.
    """
    n = 0
    for ch in mayusculas_ascii(cuerpo):
        if "A" <= ch <= "Z":
            digitos = str(ord(ch) - 64)
        elif "0" <= ch <= "9":
            digitos = ch
        else:
            continue
        for d in digitos:
            n = (n * 10 + int(d)) % modulo
    return n


def esperado(cuerpo: str, perfil: dict | None = None) -> str:
    """Control válido como texto: base − (multiplicador·N mod módulo), de 2 a 98 (ISO 7064 MOD 97-10).

    Equivale a (1 − 3N) mod 97 con 0→97, salvo cuando N es múltiplo de 97: el control es 98
    (confirmado en #5076; antes se creía que esos cuerpos no tenían control válido).
    """
    c = (perfil or reglas.activo())["control"]
    n = _n_modulo(cuerpo, c["modulo"])
    return str(c["base"] - (c["multiplicador"] * n) % c["modulo"])


def forma_valida(control: str, perfil: dict | None = None) -> bool:
    patron = (perfil or reglas.activo())["formatos"]["control"]
    return re.fullmatch(patron, control) is not None


def firmar(cuerpo: str, perfil: dict | None = None) -> str:
    """Devuelve 'cuerpo;control'."""
    return f"{cuerpo};{esperado(cuerpo, perfil)}"
