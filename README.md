# La caja negra — reemplazo

Reemplazo, escrito en FastAPI, de un servicio HTTP antiguo sin documentación («Reto 2 · La caja negra»). Responde igual que el original, errores incluidos: mismos status, mismos cuerpos y mismo orden de validación. Se explora el original con scripts propios (`test-original-app/`) y lo aprendido queda documentado en `docs/`.

Diseño y decisiones: [docs/diseno.md](docs/diseno.md). Especificación exacta (rutas, orden de errores, mensajes, comandos): [docs/anexo-referencia-tecnica.md](docs/anexo-referencia-tecnica.md).

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `app/` | El reemplazo; es lo único que se despliega. |
| `app/main.py` | FastAPI: ruta comodín, router y autenticación. |
| `app/core/` | Pipeline de validación, dígito de control y sugerencia de comandos. |
| `app/comandos/` | Un archivo por comando y el registro comando → handler. |
| `app/estado/` | Estado en memoria por token. |
| `app/respuestas/` | Formato exacto de las respuestas y rarezas del original. |
| `app/config/` | Reglas versionadas (`reglas.py`) y variables de entorno (`settings.py`). |
| `app/captura.py` | Escribe a stdout una línea `CAPTURA {...}` por request (nunca el token). |
| `tests/unit/` | Control, orden de errores, sugerencia y estado. |
| `tests/regresion/` | Reproduce `test-original-app/experimentos.jsonl` contra la app. |
| `tests/humo_local.py` | Pruebas de humo por HTTP real contra un servidor levantado. |
| `tools/` | Scripts que comparan el reemplazo con el original (`rutas.py`, `diferencial.py`, `confirmar.py`, `profundidad.py`); usan `test-original-app/helper`, nunca los importa `app/`. |
| `test-original-app/` | Exploración del original: reglas del reto, cliente, log de experimentos y hallazgos. |
| `docs/` | Diseño, anexo técnico y diagrama de arquitectura. |

Nota: el esquema de carpetas de la sección 4 de `docs/diseno.md` es anterior; manda esta estructura.

## Instalar

```
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.txt` solo tiene lo que necesita la app (fastapi, uvicorn); `requirements-dev.txt` añade pytest y las librerías de `test-original-app/`.

## Correr la app en local

```
# PowerShell
$env:TOKEN_EQUIPO="mi-token"; uvicorn app.main:app --port 8000 --workers 1
# bash
TOKEN_EQUIPO=mi-token uvicorn app.main:app --port 8000 --workers 1
```

Todas las llamadas llevan `Authorization: Bearer <TOKEN_EQUIPO>`. Un solo proceso: el estado vive en memoria.

## Pruebas

```
pytest                         # todo (unitarias + regresión)
pytest tests/unit              # unitarias
pytest tests/regresion         # imprime el % de coincidencia con el log y los ids que fallan
TOKEN_EQUIPO=mi-token python tests/humo_local.py   # humo contra la app ya levantada en :8000
```

La regresión envía cada línea del log con su método, ruta y auth, respetando los resets, y compara status y cuerpo con las reglas del reto. Excluye una línea que el log no puede representar (#248, ver el anexo, sección 9).

## Cambiar el perfil de reglas

Todo lo que puede cambiar si el original cambia (mensajes, códigos, límites, orden de validación) está en `app/config/reglas.py` dentro de `PERFILES`. Para un cambio, añade un perfil que herede de `v1` y sobrescriba solo lo que cambie:

```python
PERFILES["v2"] = {"hereda": "v1", "limites": {"limite_transfer": 50000}}
```

y actívalo con la variable de entorno `VERSION_REGLAS=v2` (por defecto `v1`).

## Despliegue en Railway

- Despliegue automático desde la rama `main`; `railway.json` ya define el comando de inicio `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` y 1 réplica.
- Variables de entorno en Railway: `TOKEN_EQUIPO` (el token del equipo) y, opcionalmente, `VERSION_REGLAS`. Ver `.env.example`.
- No hay `healthcheckPath`: `/health` exige token, igual que el original.
- No se despliega nada de `test-original-app/` ni de `tests/`.
