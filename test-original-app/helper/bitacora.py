"""El log de experimentos (experimentos.jsonl) con el formato que pide el README."""

import json
from pathlib import Path
from typing import Any

from filelock import FileLock
from pydantic import BaseModel

# Campos fuera del formato del README: solo se escriben cuando tienen valor.
OPCIONALES = ("conclusion", "metodo", "ruta", "auth", "hora")


class Experimento(BaseModel):
    id: int
    seq: str
    x_req: str | None
    hipotesis: str
    request: Any
    status: int
    response: Any
    conclusion: str | None = None
    metodo: str | None = None
    ruta: str | None = None
    auth: str | None = None
    hora: str | None = None

    def a_json(self) -> str:
        datos = self.model_dump()
        for campo in OPCIONALES:
            if datos[campo] is None:
                del datos[campo]
        return json.dumps(datos, ensure_ascii=False)


class Bitacora:
    """Agrega líneas con id consecutivo. El lock permite varios procesos escribiendo a la vez."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(f"{ruta}.lock")

    def leer(self) -> list[Experimento]:
        if not self.ruta.exists():
            return []
        with self.ruta.open(encoding="utf-8") as f:
            return [Experimento.model_validate_json(linea) for linea in f if linea.strip()]

    def seq_actual(self) -> str:
        experimentos = self.leer()
        return experimentos[-1].seq if experimentos else "s0"

    def agregar(self, *, nueva_seq: bool, seq: str, **campos) -> Experimento:
        with self._lock:
            experimentos = self.leer()
            siguiente_id = max((e.id for e in experimentos), default=0) + 1
            if nueva_seq:
                ultima = max((int(e.seq.lstrip("s") or 0) for e in experimentos), default=0)
                seq = f"s{ultima + 1}"
            experimento = Experimento(id=siguiente_id, seq=seq, **campos)
            with self.ruta.open("a", encoding="utf-8") as f:
                f.write(experimento.a_json() + "\n")
            return experimento

    def concluir(self, id_linea: int, texto: str) -> None:
        with self._lock:
            experimentos = self.leer()
            objetivo = next((e for e in experimentos if e.id == id_linea), None)
            if objetivo is None:
                raise KeyError(f"No existe la línea con id {id_linea}")
            objetivo.conclusion = texto
            self.ruta.write_text("".join(e.a_json() + "\n" for e in experimentos), encoding="utf-8")
