import pytest
from fastapi.testclient import TestClient

from app.estado.estado import almacen

TOKEN = "token-de-prueba"


def codigo(r):
    """Código de error de una respuesta (None si no es un error)."""
    j = r.json()
    return j.get("error") if isinstance(j, dict) else None


def cuenta(api, nombre="Ana"):
    """Crea una cuenta y devuelve su id."""
    r = api.msg(f"ALTA;{nombre}")
    assert r.status_code == 201
    return r.json()["cuentaId"]


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("TOKEN_EQUIPO", TOKEN)
    monkeypatch.delenv("VERSION_REGLAS", raising=False)
    almacen.vaciar()
    yield
    almacen.vaciar()


@pytest.fixture
def client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


@pytest.fixture
def api(client):
    """Helper: reset + envío de mensajes firmados."""
    from app.core.control import firmar

    class Api:
        def reset(self):
            return client.post("/__reset", headers=self.auth)

        auth = {"Authorization": f"Bearer {TOKEN}"}

        def raw(self, cuerpo: bytes | str, **kw):
            if isinstance(cuerpo, str):
                cuerpo = cuerpo.encode("utf-8")
            return client.post("/msg", content=cuerpo, headers=kw.pop("headers", self.auth))

        def msg_crudo(self, m: str):
            import json
            return self.raw(json.dumps({"m": m}, ensure_ascii=False))

        def msg(self, cuerpo: str):
            """Firma el cuerpo y lo envía."""
            return self.msg_crudo(firmar(cuerpo))

    a = Api()
    a.reset()
    return a
