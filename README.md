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
| `tools/` | Scripts propios que comparan el reemplazo con el original (rutas, pruebas diferenciales, confirmación de pendientes y la investigación del cambio v2 `fr0153_*`); usan `test-original-app/helper`, nunca los importa `app/`. |
| `test-original-app/` | Exploración del original: reglas del reto, cliente, log de experimentos y hallazgos. |
| `docs/` | Diseño, anexo técnico y diagrama de arquitectura. |

Nota: el esquema de carpetas de la sección 4 de `docs/diseno.md` es anterior; manda esta estructura.

## Entregables del reto

| Entregable | Archivo |
| --- | --- |
| Entrypoint (desplegado) | `https://la-caja-negra-production.up.railway.app` (perfil v2) |
| Especificación del servicio | [test-original-app/hallazgos.md](test-original-app/hallazgos.md) |
| Log de experimentos | [test-original-app/experimentos.jsonl](test-original-app/experimentos.jsonl) |

La carpeta `entrega/` (no versionada) tiene copias de la especificación y el log con nombres listos para subir.

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

La regresión envía cada línea del log con su método, ruta y auth, respetando los resets, y compara status y cuerpo con las reglas del reto. Detecta el punto en que el original cambió a v2 y reproduce cada línea contra su perfil (v1 antes del cambio, v2 después). Excluye cuatro líneas que el log no puede representar con fidelidad (#248, #3437, #3645, #4637; ver el anexo, sección 9).

## Cambiar el perfil de reglas

Todo lo que puede cambiar si el original cambia (mensajes, códigos, límites, orden de validación) está en `app/config/reglas.py` dentro de `PERFILES`. Un perfil hereda de otro con `"hereda"` y sobrescribe solo lo que cambie; se activa con la variable `VERSION_REGLAS` (por defecto `v1`).

El original **cambió una vez durante el día** (ver sección 6 de la especificación). Ese cambio ya está implementado en el perfil `v2`, que hereda de `v1` y sobrescribe tres cosas: el límite de TRANSFER (100000 → 50000), el formato del saldo en CONSULTA (entero → texto `"X.XX"`) y E510 (409 → 423 con el campo `intentos`). **En producción (Railway) corre `VERSION_REGLAS=v2`.** Si el original volviera a cambiar, se añade un perfil nuevo que herede de `v2`.

## Despliegue en Railway

- Despliegue automático desde la rama `main`; `railway.json` ya define el comando de inicio `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` y 1 réplica.
- Variables de entorno en Railway: `TOKEN_EQUIPO` (el token del equipo) y, opcionalmente, `VERSION_REGLAS`. Ver `.env.example`.
- No hay `healthcheckPath`: `/health` exige token, igual que el original.
- No se despliega nada de `test-original-app/` ni de `tests/`.
