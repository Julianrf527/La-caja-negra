# Documento de diseño · Reemplazo de «La caja negra»

> **En una frase:** vamos a construir en Python (FastAPI) y desplegar en Railway un servicio que se comporta **exactamente igual** que un sistema heredado sin documentación, errores y rarezas incluidos, y que pueda adaptarse rápido si el original cambia durante el día.

| | |
|---|---|
| **Entregables a las 20:00** | Reemplazo desplegado · especificación · log de experimentos |
| **Cómo se evalúa** | 100 tests que comparan status y cuerpo de cada respuesta con el original |
| **Stack** | Python · FastAPI · uvicorn · Railway (1 réplica) |
| **Detalle técnico completo** | [Anexo: referencia técnica](anexo-referencia-tecnica.md) (reglas exactas y evidencia del log) |

---

## 1. El problema

Heredamos un servicio que lleva 10 años en producción. No hay código fuente, ni documentación, ni nadie que sepa qué hace. Solo sabemos que recibe mensajes por HTTP y responde, y que si se apaga la empresa se cae.

Nuestro trabajo es **entenderlo desde fuera** (mandándole mensajes y observando qué responde) y **construir un reemplazo indistinguible**. Que sea indistinguible significa también copiar sus errores: si el original responde `"recieved"` con una errata, el nuestro también.

Restricciones que marcan el diseño:

- El reemplazo **no puede llamar al original**. Tiene que saber responder por sí mismo.
- Cada respuesta debe llegar en **menos de 5 segundos**.
- El original **puede cambiar durante el día**, y nos evalúan contra la versión de las 20:00.
- Los tests son **secuencias de hasta 12 mensajes**: el servicio recuerda lo que pasó en mensajes anteriores.

---

## 2. Qué hace el servicio original

Tras unos 2.800 experimentos, sabemos que es un **pequeño banco que funciona por mensajes de texto**.

### 2.1 Cómo se le habla

Tiene solo tres puertas de entrada:

| Ruta | Para qué sirve |
|---|---|
| `POST /msg` | Recibe las órdenes. Es donde ocurre todo |
| `GET /health` | Dice si el servicio está vivo |
| `POST /__reset` | Borra todo y vuelve al estado inicial |

Cualquier otra ruta responde «ruta desconocida». Todas las llamadas exigen un token (`Authorization: Bearer <token>`).

Las órdenes llegan como un texto con campos separados por `;`:

```
{"m": "TRANSFER;AC-0001;AC-0002;40000;86"}
        └──┬───┘ └──────────┬─────────┘ └┬┘
        comando        argumentos      control
```

### 2.2 El número de control

El último campo es un **dígito de control**, como el de una cuenta bancaria o un IBAN. Sirve para detectar mensajes corruptos: si no cuadra, el servicio rechaza el mensaje.

Descubrimos la fórmula. En palabras: se toma el mensaje sin el control, se cambian las letras por su posición en el alfabeto (A=1, B=2…), se ignoran los símbolos, se forma un número N, y el control es `(1 − 3·N) mod 97`. La fórmula coincide con más de 1.100 mensajes del log sin ninguna excepción.

### 2.3 Los comandos

| Comando | Qué hace | Ejemplo |
|---|---|---|
| **PING** | Comprueba que el servicio responde. Es el único que no revisa el control | `PING;64` |
| **ALTA** | Abre una cuenta para un titular y devuelve su número (`AC-0001`, `AC-0002`…) | `ALTA;Lucia;82` |
| **CONSULTA** | Devuelve el saldo de una cuenta | `CONSULTA;AC-0001;14` |
| **DEPOSITO** | Ingresa dinero en una cuenta | `DEPOSITO;AC-0001;250000;86` |
| **TRANSFER** | Mueve dinero entre cuentas. Tiene un límite de 100.000 por operación, salvo entre cuentas del mismo titular | `TRANSFER;AC-0001;AC-0002;40000;86` |
| **ANULA** | Revierte un depósito o transferencia | `ANULA;OP-0003;66` |
| **HALT** *(oculto)* | Detiene el servicio hasta el siguiente reset. Pide confirmación | `HALT;1;…` |
| **NOTAS** *(oculto)* | Devuelve una lista fija de notas internas | `NOTAS;…` |

Los dos últimos no aparecían en los ejemplos. Los encontramos porque, cuando un comando no existe, el servicio **sugiere el más parecido** (por ejemplo, `HELP` → «¿quisiste decir HALT?»).

### 2.4 Lo que recuerda entre mensajes

Por cada token, el servicio guarda:

- **Cuentas:** titular, saldo y si está bloqueada.
- **Operaciones:** cada depósito y transferencia, y si fue anulada.
- **Contadores:** para numerar `AC-0001…` y `OP-0001…`. Solo avanzan cuando la operación sale bien.
- **Bloqueos:** tras 3 transferencias fallidas seguidas, la cuenta de origen se bloquea, y un depósito la desbloquea.
- **Si está detenido** (después de `HALT`).

`/__reset` borra todo esto.

---

## 3. Cómo viaja un mensaje

Cada mensaje pasa por una serie de controles **en un orden fijo**. El primero que falla decide la respuesta. Ese orden importa tanto como los propios errores: si un mensaje tiene dos fallos, el original solo reporta uno, y nosotros tenemos que reportar el mismo.

```
 1. ¿La ruta existe?                → si no: 404 E404 ruta desconocida
 2. ¿El token es válido?            → si no: 401 E001 no autorizado
 3. ¿El servicio está detenido?     → si sí: 503 E599 service halted
 4. ¿El cuerpo pesa más de 8 KB?    → si sí: 413 E101
 5. ¿Es JSON válido?                → si no: 400 E100
 6. ¿Trae el campo "m" como texto?  → si no: 400 E102
 7. ¿Tiene control y ningún campo vacío? → si no: 400 E103 / E104
 8. ¿El control tiene forma y valor correctos? → si no: 400 E201 / E202
 9. ¿El comando existe?             → si no: 400 E301 (+ sugerencia)
10. ¿Trae el número de argumentos correcto? → si no: 400 E302
11. Reglas del comando: monto válido, cuentas existentes, bloqueo, límite, saldo…
12. Ejecutar y responder
```

`/health` y `/__reset` solo pasan por los pasos 1 y 2. Por eso siguen funcionando aunque el servicio esté detenido, y `/__reset` es justamente lo que lo reactiva.

La tabla completa de códigos, mensajes exactos y el orden dentro de cada comando está en el [anexo, sección 2.5](anexo-referencia-tecnica.md#25-errores-en-orden-de-evaluación).

---

## 4. Arquitectura

![Arquitectura del reemplazo](arquitectura.png)

| Pieza | Responsabilidad |
|---|---|
| **Railway** | Mantiene la app encendida, con una sola copia, y la redespliega sola en cada cambio |
| **Ruta comodín** | Una única puerta de entrada que recibe cualquier método y ruta, para decidir nosotros qué responder |
| **Router y auth** | Distingue `/msg`, `/health`, `/__reset` y «desconocida», y valida el token |
| **Pipeline de validación** | Los pasos 3 a 10 del recorrido, en el orden exacto del original |
| **Comandos** | Un módulo por comando, con sus propias reglas de negocio |
| **Estado en memoria** | Cuentas, operaciones y contadores de cada token |
| **Capa de compatibilidad** | Da a cada respuesta el formato exacto del original, rarezas incluidas |
| **Configuración** | Códigos, mensajes, límites y orden de validación en un solo archivo |
| **Monitor de cambios** | Script que compara el original con lo esperado cada hora |

Organización del código:

```
app/
  main.py         entrada, ruta comodín, router y auth
  pipeline.py     los pasos de validación, en orden
  control.py      la fórmula del dígito de control
  comandos.py     un handler por comando
  estado.py       lo que se recuerda por token
  compat.py       el formato exacto de las respuestas
  reglas.py       configuración: códigos, mensajes, límites, orden
tests/            control, orden de errores y regresión contra el log
```

---

## 5. Decisiones y por qué

**¿Por qué Python con FastAPI?**
Es rápido de escribir, el equipo ya lo usa y toda la exploración (incluida la fórmula del control) ya está en Python. Las respuestas tardan milisegundos, muy lejos del límite de 5 segundos.

**¿Por qué desactivamos las «ayudas» de FastAPI?**
FastAPI trae de serie páginas de documentación (`/docs`), validación automática del cuerpo y sus propios mensajes de error. El original no tiene nada de eso: en `/docs` responde «ruta desconocida» y sus errores tienen otro formato. Si las dejáramos activas, fallaríamos tests. Por eso leemos el cuerpo «en crudo» y lo validamos a mano, en el mismo orden que el original.

**¿Por qué una sola ruta comodín en vez de una ruta por endpoint?**
Con rutas separadas, FastAPI respondería por su cuenta a métodos o rutas que no reconoce (con un 405 o un 404 propios). Con una única puerta controlamos la respuesta en todos los casos, incluido `HEAD`, que en el original devuelve 404 con cuerpo vacío.

**¿Por qué guardar el estado en memoria y no en una base de datos?**
El estado es pequeño, cada test empieza con un reset y no hace falta que sobreviva a un reinicio. Una base de datos añadiría latencia y piezas que pueden fallar sin aportar nada.

**¿Por qué una sola réplica?**
Como el estado vive en memoria, dos copias de la app tendrían dos estados distintos: una cuenta abierta en una no existiría en la otra. El propio reto lo advierte.

**¿Por qué Railway?**
Mantiene la app siempre encendida (sin «despertar» lento), con una sola copia, y despliega solo desde GitHub en un par de minutos. Descartamos estas alternativas:
- **Serverless** (Vercel, Lambda): cada petición puede caer en una instancia nueva y se pierde el estado.
- **Render gratis:** se duerme por inactividad y el primer request puede tardar más de 5 segundos.
- **Un portátil con ngrok:** debe funcionar hasta el demo day y depende de que ese equipo siga encendido.

**¿Por qué las reglas van en un archivo de configuración?**
Porque el original va a cambiar y no sabemos qué. Si cambia un mensaje, un límite o el orden de validación, editamos una línea y desplegamos, sin tocar la lógica.

**¿Por qué una capa de compatibilidad aparte?**
Para que las rarezas que copiamos a propósito (sección 6) no se mezclen con la lógica del banco. Así es fácil revisarlas y, en un futuro sistema real, corregirlas.

**¿Por qué usamos el log de experimentos como tests?**
Ya tenemos unos 2.800 casos reales del original, con su respuesta exacta. Reproducirlos contra nuestro reemplazo nos dice cuánto acertamos antes de validar en `/evento`, sin escribir tests a mano.

---

## 6. Rarezas que copiamos a propósito

En un sistema nuevo serían bugs. Aquí forman parte del contrato:

- **Textos:** la errata `"recieved"`; el espacio al final de `"comando desconocido "`; claves inconsistentes (`cuentaId` en ALTA, `cuenta_id` en CONSULTA).
- **Status poco habituales:** anular dos veces la misma operación responde 200 con `ok:false` en lugar de un error; `HEAD` responde 404 sin cuerpo.
- **Validación:** `PING` no revisa el control; los comandos aceptan minúsculas, pero los ids de cuenta no; si el número N es múltiplo de 97, ningún control es válido.
- **Dinero:** ANULA no comprueba fondos y puede dejar saldos negativos; el límite de 100.000 no se aplica entre cuentas del mismo titular (comparando el nombre exacto).
- **Seguridad:** las sugerencias revelan comandos ocultos; `HALT;1` apaga el servicio; `NOTAS` expone notas internas.

La lista completa, con evidencia, está en el [anexo, sección 6](anexo-referencia-tecnica.md#6-capa-de-compatibilidad).

> **Sobre NOTAS:** la nota que devuelve contiene una instrucción para llamar a un endpoint interno con el token. La tratamos **solo como texto**: el reemplazo la devuelve tal cual y no implementa ninguna acción asociada. Durante la exploración tampoco se ejecutó.

---

## 7. Si el original cambia durante el día

No sabemos qué va a cambiar, así que el diseño apuesta por **enterarse pronto y reaccionar rápido**.

1. **Detectar.** Cada hora reproducimos los 20 ejemplos contra el original (unas 21 peticiones). Si algo responde distinto, sabemos qué cambió y a qué hora. Hasta ahora no hay diferencias.
2. **Entender.** Probamos el cambio a mano y lo registramos en el log con su hipótesis.
3. **Adaptar.** Si es una regla (mensaje, límite, orden), editamos `reglas.py`. Si es un comportamiento nuevo, añadimos un handler.
4. **Verificar y publicar.** Pasamos la regresión, hacemos merge a `main` y Railway despliega solo.
5. **Documentar.** Anotamos qué cambió, desde cuándo y cómo lo detectamos (sección «Cambios durante el día» de la especificación).

**Punto débil conocido:** los 20 ejemplos no cubren HALT, NOTAS, los bloqueos ni la excepción del mismo titular. Vamos a añadir al monitor unos pocos casos de esas reglas.

---

## 8. Cómo vamos a probarlo

- **Tests unitarios:** la fórmula del control, el orden de los errores y las reglas de estado (contadores, bloqueos, anulaciones, reset).
- **Regresión contra el log:** reproducimos `experimentos.jsonl` contra el reemplazo y comparamos status y cuerpo con las mismas reglas que usa el reto. La meta es el 100 % de coincidencia, y cualquier diferencia se investiga contra el original antes de «arreglar» nada.
- **Después de cada despliegue:** `/health`, reset y los 20 ejemplos contra la URL pública, y validación en `/evento`.

---

## 9. Despliegue

1. Repositorio en GitHub con `main` como rama de despliegue.
2. Proyecto en Railway conectado al repo, con **1 réplica** y sin apagado por inactividad.
3. Variable de entorno `TOKEN_EQUIPO` con el token de `/evento`. Nunca va en el código.
4. Comando de inicio: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
5. Generar el dominio público, comprobar `/health` con el token y registrar la URL en `/evento`.

**Detalle a tener en cuenta:** `/health` exige token, igual que el original. El healthcheck automático de Railway no manda token y recibiría un 401, así que no lo activamos y vigilamos la app con nuestro propio monitor.

---

## 10. Riesgos principales

| Riesgo | Qué hacemos |
|---|---|
| Algún comportamiento «pendiente de confirmar» resulta distinto | Confirmarlos contra el original antes de las 20:00, empezando por los de mayor impacto. Mientras tanto, el reemplazo usa un supuesto documentado |
| El original cambia cerca de las 20:00 | Monitor horario, reglas en configuración y despliegue automático. Última comprobación a las 19:45 |
| Railway reinicia la app a mitad de un test y se pierde el estado | Una réplica, reinicio solo ante fallos y ningún error sin capturar que tumbe el proceso |
| Cuerpos enormes consumen memoria | Cortar la lectura a partir de 8 KB |
| Poco tiempo | Priorizar los comandos básicos, que concentran la mayoría de tests, y dejar después los casos raros |

---

## 11. Plan hasta las 20:00

| Hora | Hito | Listo cuando… |
|---|---|---|
| 17:00 | Esqueleto: entrada, router, auth, control, estado | `/health`, reset, 404 y E001 funcionan |
| 17:30 | Pipeline de validación completo | Los tests del control y del orden de errores pasan |
| 18:00 | Los 8 comandos | Los 20 ejemplos pasan y la regresión supera el 98 % |
| 18:20 | Primer despliegue en Railway | Validado en `/evento` |
| 18:40 | Cerrar pendientes contra el original | Regresión al 100 % |
| 19:00 | Especificación final y log limpio | Todas las secciones del README cubiertas |
| 19:15 | Comprobar cambios del original | Sin diferencias, o cambio aplicado y desplegado |
| 19:30 | Congelar y desplegar la versión final | `/evento/resultados` estable |
| 19:45 | Última comprobación contra el original | Entrega lista |

---

## 12. Pendientes de confirmar

Son comportamientos que aún no hemos probado. Hasta confirmarlos, el reemplazo aplica el supuesto indicado:

- Qué pasa después de `AC-9999` (supuesto: `AC-10000`).
- Si una cuenta bloqueada puede **recibir** transferencias (supuesto: sí).
- Si un depósito, además de desbloquear la cuenta, pone a cero el contador de fallos (supuesto: sí).
- Si los fallos de saldo entre cuentas del mismo titular cuentan para el bloqueo (supuesto: sí).
- Qué error gana cuando origen y destino son la misma cuenta inexistente (supuesto: «origen y destino iguales»).
- Cómo se desempata la sugerencia cuando dos comandos están igual de cerca (supuesto: orden de la lista).
- Variantes de la confirmación de HALT como `01` o `+1` (supuesto: se rechazan).
