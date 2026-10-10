"""Cliente HTTP del servicio original. Cada request queda registrado en la bitácora."""

import json
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .bitacora import Bitacora, Experimento
from .config import Config

TOKEN_PROPIO = object()  # valor por defecto de `auth`: usa el token del .env
SIN_CUERPO = object()


class RateLimitado(Exception):
    """La infraestructura respondió con X-Frontier-Infra: rate-limit (no es del servicio)."""


class LimiteDeRequests(Exception):
    """Se alcanzó el máximo de requests configurado para una ejecución."""


def _parsear(texto: str) -> Any:
    try:
        return json.loads(texto)
    except ValueError:
        return texto


class Cliente:
    def __init__(self, config: Config | None = None, max_requests: int | None = None):
        self.config = config or Config()
        self.bitacora = Bitacora(self.config.log)
        self.seq = self.bitacora.seq_actual()
        self._http = httpx.Client(base_url=self.config.url, timeout=self.config.timeout)
        self._ultimo_envio = 0.0
        self.max_requests = max_requests
        self.enviados = 0
        self.ultima_respuesta: httpx.Response | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    @property
    def token(self) -> str:
        return self.config.token.get_secret_value()

    def _esperar_turno(self) -> None:
        espera = 1 / self.config.max_rps - (time.monotonic() - self._ultimo_envio)
        if espera > 0:
            time.sleep(espera)
        self._ultimo_envio = time.monotonic()

    @retry(
        retry=retry_if_exception_type(RateLimitado),
        wait=wait_exponential(min=1, max=30),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _enviar(self, metodo: str, ruta: str, contenido: bytes | None, headers: dict) -> httpx.Response:
        if self.max_requests is not None and self.enviados >= self.max_requests:
            raise LimiteDeRequests(f"se alcanzó el máximo de {self.max_requests} requests")
        self._esperar_turno()
        self.enviados += 1
        respuesta = self._http.request(metodo, ruta, content=contenido, headers=headers)
        if respuesta.headers.get("x-frontier-infra") == "rate-limit":
            raise RateLimitado(f"{metodo} {ruta}")
        return respuesta

    def raw(
        self,
        metodo: str,
        ruta: str,
        hipotesis: str,
        *,
        cuerpo: Any = SIN_CUERPO,
        cuerpo_crudo: str | None = None,
        auth: Any = TOKEN_PROPIO,
        content_type: str | None = "application/json",
        conclusion: str | None = None,
    ) -> Experimento:
        """Manda cualquier request al original y lo registra.

        cuerpo:       objeto que se envía como JSON.
        cuerpo_crudo: texto que se envía tal cual (JSON roto, vacío, etc.).
        auth:         por defecto el token del .env; None = sin header;
                      un string = valor completo del header (p. ej. "Bearer falso").
        content_type: None = no manda Content-Type.
        """
        metodo = metodo.upper()
        if cuerpo is not SIN_CUERPO:
            cuerpo_crudo = json.dumps(cuerpo, ensure_ascii=False)

        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if auth is TOKEN_PROPIO:
            headers["Authorization"] = f"Bearer {self.token}"
        elif auth is not None:
            headers["Authorization"] = auth

        contenido = cuerpo_crudo.encode() if cuerpo_crudo is not None else None
        respuesta = self._enviar(metodo, ruta, contenido, headers)
        self.ultima_respuesta = respuesta

        es_reset = (metodo, ruta) == ("POST", "/__reset")
        es_normal = (metodo, ruta) == ("POST", "/msg")
        fecha = respuesta.headers.get("date")
        if auth is TOKEN_PROPIO:
            auth_log = None
        elif auth is None:
            auth_log = "(sin header)"
        else:
            auth_log = auth.replace(self.token, "<token>")  # nunca escribir el token en el log

        experimento = self.bitacora.agregar(
            nueva_seq=es_reset,
            seq=self.seq,
            x_req=respuesta.headers.get("x-req"),
            hipotesis=hipotesis,
            request=_parsear(cuerpo_crudo) if cuerpo_crudo is not None else None,
            status=respuesta.status_code,
            response=_parsear(respuesta.text),
            conclusion=conclusion,
            metodo=None if es_normal else metodo,
            ruta=None if es_normal else ruta,
            auth=auth_log,
            hora=parsedate_to_datetime(fecha).isoformat() if fecha else None,
        )
        self.seq = experimento.seq
        return experimento

    def msg(self, m: str, hipotesis: str, conclusion: str | None = None) -> Experimento:
        return self.raw("POST", "/msg", hipotesis, cuerpo={"m": m}, conclusion=conclusion)

    def reset(self, hipotesis: str = "reset antes de una secuencia nueva") -> Experimento:
        return self.raw("POST", "/__reset", hipotesis)

    def health(self, hipotesis: str = "el servicio está vivo") -> Experimento:
        return self.raw("GET", "/health", hipotesis)


# ---------------------------------------------------------------------------
# Exploración automática
# ---------------------------------------------------------------------------

COMANDOS_CONOCIDOS = ("PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA")
COMANDOS_CANDIDATOS = (
    "SALDO", "SALDOS", "BAJA", "RETIRO", "HISTORIAL", "LISTA", "ESTADO", "CIERRE",
    "HELP", "AYUDA", "VERSION", "RESET", "ECHO", "BLOQUEA", "DESBLOQUEA", "REVERSA",
)
METODOS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
RUTAS = ("/", "/msg", "/msg/", "/MSG", "/health", "/health/", "/__reset", "/nope", "/admin", "/version", "/openapi.json", "/docs")
CODIGOS_CONTROL = ("E201", "E202")  # control mal formado / inválido (según ejemplos.jsonl)


def _es_error(e: Experimento, *codigos: str) -> bool:
    return isinstance(e.response, dict) and e.response.get("error") in codigos


class Explorador:
    """Baterías de experimentos sobre el original. Todo queda en la bitácora vía Cliente.

    Uso típico (cada fase empieza con reset para no depender de estado previo):
        with Cliente() as c:
            x = Explorador(c)
            x.http(); x.integridad(); x.descubrir_control(); x.comandos(); x.memoria()
    """

    def __init__(self, cliente: Cliente):
        self.c = cliente
        self.muestras_control: list[tuple[str, str]] = []  # (payload sin control, control válido)
        self.formula = None  # callable(payload) -> str, cuando se conozca
        self.hallazgos: dict[str, Any] = {}

    # --- utilidades ------------------------------------------------------
    def _firmar(self, payload: str) -> str:
        """Devuelve 'payload;control' con control válido (fórmula o búsqueda por fuerza bruta)."""
        if self.formula is not None:
            return f"{payload};{self.formula(payload)}"
        return f"{payload};{self.buscar_control(payload)}"

    def buscar_control(self, payload: str) -> str | None:
        """Prueba controles 0..99 hasta que el servicio deje de quejarse del control.

        Ojo: si el comando tiene efectos, el primer control válido los ejecuta una vez.
        """
        for muestra, control in self.muestras_control:
            if muestra == payload:
                return control
        for n in range(100):
            for control in (str(n),):
                e = self.c.msg(f"{payload};{control}", f"buscar control válido de '{payload}': probar {control}")
                if not _es_error(e, *CODIGOS_CONTROL):
                    self.muestras_control.append((payload, control))
                    self.c.bitacora.concluir(e.id, f"control válido para '{payload}' = {control}")
                    return control
        return None

    def _probar(self, m: str, hipotesis: str) -> Experimento:
        return self.c.msg(m, hipotesis)

    # --- 1. Entrada ------------------------------------------------------
    def http(self) -> None:
        """Rutas, métodos, autenticación, forma del cuerpo y límites."""
        c = self.c
        c.reset("fase http: estado inicial")
        for ruta in RUTAS:
            for metodo in METODOS:
                if (metodo, ruta) == ("POST", "/__reset"):
                    continue
                c.raw(metodo, ruta, f"{metodo} {ruta}: ¿existe y cómo responde?",
                      cuerpo_crudo='{"m": "PING;64"}' if metodo in ("POST", "PUT", "PATCH") else None)

        for etiqueta, auth in (
            ("sin header Authorization", None),
            ("token falso", "Bearer falso"),
            ("esquema en minúsculas", f"bearer {c.token}"),
            ("sin esquema Bearer", c.token),
            ("Bearer sin token", "Bearer"),
            ("esquema Basic", f"Basic {c.token}"),
            ("token con espacio extra", f"Bearer  {c.token}"),
        ):
            for metodo, ruta in (("POST", "/msg"), ("GET", "/health"), ("POST", "/__reset"), ("GET", "/nope")):
                c.raw(metodo, ruta, f"auth ({etiqueta}) en {metodo} {ruta}", cuerpo_crudo='{"m": "PING;64"}' if metodo == "POST" else None, auth=auth)
        c.reset("fase http: el reset sin token no debe haber cambiado nada, volver a empezar")

        cuerpos = {
            "vacío": "", "JSON roto": '{"m": "PING;64"', "null": "null", "lista": "[]",
            "objeto vacío": "{}", "m numérico": '{"m": 1}', "m null": '{"m": null}',
            "m lista": '{"m": ["PING;64"]}', "m vacío": '{"m": ""}', "clave M mayúscula": '{"M": "PING;64"}',
            "clave extra": '{"m": "PING;64", "x": 1}', "string JSON": '"PING;64"', "texto plano": "PING;64",
            "claves duplicadas": '{"m": "x", "m": "PING;64"}', "BOM/espacios": '  {"m": "PING;64"}  ',
        }
        for etiqueta, cuerpo in cuerpos.items():
            c.raw("POST", "/msg", f"cuerpo {etiqueta}", cuerpo_crudo=cuerpo)
        for ct in (None, "text/plain", "application/x-www-form-urlencoded", "application/json; charset=utf-8"):
            c.raw("POST", "/msg", f"Content-Type={ct}", cuerpo_crudo='{"m": "PING;64"}', content_type=ct)

        for tam in (100, 1_000, 10_000, 100_000, 1_000_000):
            c.raw("POST", "/msg", f"límite de tamaño de m: {tam} caracteres", cuerpo={"m": "A" * tam})
        c.reset("fase http terminada")

    # --- 2. Integridad ---------------------------------------------------
    def integridad(self) -> None:
        """Cómo valida el servicio el campo de control (último campo)."""
        c = self.c
        c.reset("fase integridad: estado inicial")
        casos = {
            "sin control (solo comando)": "PING",
            "solo separador": ";",
            "mensaje vacío": "",
            "espacios": " ",
            "control vacío": "PING;",
            "control letra": "PING;X",
            "control con letra al final": "PING;6X",
            "control negativo": "PING;-1",
            "control con signo +": "PING;+64",
            "control con ceros a la izquierda": "PING;064",
            "control decimal": "PING;64.0",
            "control con espacios": "PING; 64",
            "control con espacio final": "PING;64 ",
            "control de 3 dígitos": "PING;640",
            "control hexadecimal": "PING;0x40",
            "control unicode (dígito árabe)": "PING;٦٤",
            "separador doble": "PING;;64",
            "separador final extra": "PING;64;",
            "comando en minúsculas": "ping;64",
            "comando mixto": "PiNg;64",
            "comando con espacios": " PING;64",
            "comando desconocido, control inválido": "XXXX;99",
            "comando desconocido, control no numérico": "XXXX;ZZ",
            "comando desconocido, control válido por probar": "XXXX;64",
        }
        for etiqueta, m in casos.items():
            self._probar(m, f"integridad: {etiqueta}")
        # PING no valida el control (acepta cualquier valor): el barrido de controles se hace con
        # CONSULTA, que no tiene efectos, en descubrir_control().
        c.reset("fase integridad terminada")

    def descubrir_control(self, payloads: list[str] | None = None) -> list[tuple[str, str]]:
        """Reúne pares (payload, control válido) usando PING con distintos argumentos.

        Con los pares se ajusta la fórmula del control fuera de línea. Asigna `self.formula` a mano.
        """
        self.c.reset("fase control: estado inicial")
        payloads = payloads or [f"CONSULTA;AC-{n:04d}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 99, 100, 1000)]
        payloads += ["CONSULTA;AC-0001", "CONSULTA;AC-A", "CONSULTA;AC-B", "CONSULTA;AB", "CONSULTA;BA", "CONSULTA;x", "CONSULTA;xx"]
        for p in payloads:
            self.buscar_control(p)
        return self.muestras_control

    # --- 3. Comandos -----------------------------------------------------
    def comandos(self) -> None:
        """Busca comandos ocultos y prueba aridad/tipos de cada comando conocido.

        Necesita `self.formula` (o paga la búsqueda por fuerza bruta en cada mensaje).
        """
        c = self.c
        c.reset("fase comandos: estado inicial")
        for cmd in COMANDOS_CANDIDATOS:
            self._probar(self._firmar(cmd), f"comando candidato {cmd}: ¿existe?")

        c.reset("fase comandos: estado limpio tras buscar comandos")
        pruebas = {
            "PING": ["PING;x", "PING;x;y"],
            "ALTA": ["ALTA", "ALTA;Ana", "ALTA;Ana;Perez", "ALTA;", "ALTA;Ana María", "ALTA;ñandú", "ALTA;" + "A" * 200,
                     "ALTA;Ana;Perez;Lopez", "ALTA;Ana", "ALTA;ana"],
            "CONSULTA": ["CONSULTA", "CONSULTA;AC-0001", "CONSULTA;ac-0001", "CONSULTA;AC-1", "CONSULTA;AC-00001",
                         "CONSULTA;AC-0001;extra", "CONSULTA;XX-0001", "CONSULTA;OP-0001", "CONSULTA;AC-0000", "CONSULTA;AC-ABCD"],
            "DEPOSITO": ["DEPOSITO", "DEPOSITO;AC-0001", "DEPOSITO;AC-0001;100", "DEPOSITO;AC-0001;0", "DEPOSITO;AC-0001;-5",
                         "DEPOSITO;AC-0001;1.5", "DEPOSITO;AC-0001;abc", "DEPOSITO;AC-0001;99999999999", "DEPOSITO;AC-0099;100",
                         "DEPOSITO;AC-0001;100;extra", "DEPOSITO;AC-0001;1000000", "DEPOSITO;AC-0001;001"],
            "TRANSFER": ["TRANSFER", "TRANSFER;AC-0001;AC-0002", "TRANSFER;AC-0001;AC-0001;1", "TRANSFER;AC-0001;AC-0002;0",
                         "TRANSFER;AC-0001;AC-0002;-1", "TRANSFER;AC-0001;AC-0099;1", "TRANSFER;AC-0099;AC-0001;1",
                         "TRANSFER;AC-0001;AC-0002;abc", "TRANSFER;AC-0001;AC-0002;1;extra"],
            "ANULA": ["ANULA", "ANULA;OP-9999", "ANULA;AC-0001", "ANULA;OP-0001;extra", "ANULA;op-0001", "ANULA;OP-1"],
        }
        for cmd, mensajes in pruebas.items():
            for p in mensajes:
                self._probar(self._firmar(p), f"comando {cmd}: {p}")
        c.reset("fase comandos terminada")

    # --- 4. Memoria ------------------------------------------------------
    def memoria(self) -> None:
        """Qué recuerda el servicio: cuentas, saldos, operaciones, límites, contadores, X-Req."""
        c = self.c
        f = self._firmar
        c.reset("fase memoria: estado inicial")
        self._probar(f("CONSULTA;AC-0001"), "sin altas, AC-0001 no existe")
        self._probar(f("ALTA;Ana"), "primera alta da AC-0001")
        self._probar(f("ALTA;Ana"), "misma alta repetida: ¿otra cuenta o duplicado?")
        self._probar(f("CONSULTA;AC-0001"), "saldo inicial")
        self._probar(f("DEPOSITO;AC-0001;100"), "depósito simple: operacionId")
        self._probar(f("CONSULTA;AC-0001"), "saldo tras depósito (¿inmediato o diferido? status 'recieved')")
        self._probar(f("CONSULTA;AC-0001"), "saldo repetido: ¿cambia con el tiempo/contador?")
        self._probar(f("ANULA;OP-0001"), "anular depósito: ¿revierte saldo?")
        self._probar(f("CONSULTA;AC-0001"), "saldo tras anular depósito")
        self._probar(f("ANULA;OP-0001"), "anular de nuevo")
        self._probar(f("PING"), "PING tras actividad: ¿sigue sin estado?")
        for i in range(12):
            self._probar(f("ALTA;U%d" % i), f"alta masiva {i}: ¿límite de cuentas, formato AC-NNNN al crecer?")
        for i in range(8):
            self._probar(f("DEPOSITO;AC-0001;50000"), f"depósitos repetidos {i}: ¿límite diario/acumulado (E506)?")
        self._probar(f("TRANSFER;AC-0001;AC-0002;1"), "transferencia mínima")
        self._probar(f("ANULA;OP-0001"), "anular op antigua tras más actividad")
        c.reset("fase memoria: tras reset, ¿vuelven contadores?")
        self._probar(f("CONSULTA;AC-0001"), "tras reset la cuenta no existe")
        self._probar(f("ALTA;Ana"), "tras reset el contador de cuentas vuelve a AC-0001")
        self._probar(f("DEPOSITO;AC-0001;5"), "tras reset el contador de operaciones vuelve a OP-0001")

    def todo(self) -> None:
        self.http()
        self.integridad()
        self.comandos()
        self.memoria()
