"""Línea de comandos para explorar la caja negra.

    python test-original-app/cli.py --help
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from helper.bitacora import Bitacora, Experimento
from helper.cliente import TOKEN_PROPIO, Cliente, Explorador, LimiteDeRequests
from helper.config import APP, RAIZ, Config

app = typer.Typer(help="Explora el servicio original y registra cada request.")
consola = Console()

Hipotesis = Annotated[str, typer.Option("--hipotesis", "-H", help="Qué estás probando")]
Conclusion = Annotated[Optional[str], typer.Option("--conclusion", "-c", help="Qué aprendiste")]


def _config() -> Config:
    try:
        return Config()
    except ValidationError:
        consola.print(f"[red]Falta CAJA_TOKEN.[/] Agrégalo en {RAIZ / '.env'} como CAJA_TOKEN=tu_token")
        raise typer.Exit(1)


def _mostrar(e: Experimento) -> None:
    color = "green" if e.status < 400 else "yellow" if e.status < 500 else "red"
    consola.print(f"[dim]id {e.id} · {e.seq} · X-Req {e.x_req}[/]  [{color}]HTTP {e.status}[/]")
    if isinstance(e.response, str):
        consola.print(repr(e.response))
    else:
        consola.print_json(json.dumps(e.response, ensure_ascii=False))


@app.callback(invoke_without_command=True)
def por_defecto(ctx: typer.Context):
    """Sin comando: comprueba el servicio y reproduce pruebas/ejemplos.jsonl."""
    if ctx.invoked_subcommand is not None:
        return
    with Cliente(_config()) as c:
        e = c.health()
        if e.status != 200:
            consola.print(f"[red]ERROR: /health respondió HTTP {e.status}: {e.response}[/]")
            raise typer.Exit(1)
        e = c.msg("PING;64", "el token propio es aceptado")
        if e.status in (401, 403):
            consola.print(f"[red]ERROR: el servicio rechazó el token (HTTP {e.status}). Revisa CAJA_TOKEN en {RAIZ / '.env'}[/]")
            raise typer.Exit(1)
    ejemplos()


@app.command()
def health(hipotesis: Hipotesis = "el servicio está vivo"):
    """GET /health"""
    with Cliente(_config()) as c:
        _mostrar(c.health(hipotesis))


@app.command()
def reset(hipotesis: Hipotesis = "reset antes de una secuencia nueva"):
    """POST /__reset y empieza una secuencia nueva en el log."""
    with Cliente(_config()) as c:
        _mostrar(c.reset(hipotesis))


@app.command()
def msg(
    m: Annotated[str, typer.Argument(help='El mensaje, p. ej. "PING;64"')],
    hipotesis: Hipotesis,
    conclusion: Conclusion = None,
):
    """POST /msg con {"m": ...}"""
    with Cliente(_config()) as c:
        _mostrar(c.msg(m, hipotesis, conclusion))


@app.command()
def raw(
    metodo: str,
    ruta: str,
    hipotesis: Hipotesis,
    body: Annotated[Optional[str], typer.Option(help="Cuerpo crudo, se manda tal cual")] = None,
    sin_token: Annotated[bool, typer.Option("--sin-token", help="No manda Authorization")] = False,
    auth: Annotated[Optional[str], typer.Option(help='Valor de Authorization, p. ej. "Bearer falso"')] = None,
    conclusion: Conclusion = None,
):
    """Cualquier método y ruta (para explorar rutas, auth y cuerpos raros)."""
    valor_auth = None if sin_token else auth if auth is not None else TOKEN_PROPIO
    with Cliente(_config()) as c:
        _mostrar(c.raw(metodo, ruta, hipotesis, cuerpo_crudo=body, auth=valor_auth, conclusion=conclusion))


@app.command()
def ejemplos(
    archivo: Annotated[Path, typer.Argument(exists=True, dir_okay=False)] = APP / "pruebas" / "ejemplos.jsonl",
):
    """Reset, reproduce ejemplos.jsonl en orden y muestra qué cambió."""
    casos = [json.loads(l) for l in archivo.read_text(encoding="utf-8").splitlines() if l.strip()]
    tabla = Table("n", "log id", "request", "esperado", "recibido")
    diferencias = 0

    with Cliente(_config()) as c:
        c.reset("reproducir ejemplos.jsonl: estado inicial")
        for caso in casos:
            e = c.raw("POST", "/msg", f"ejemplo {caso['n']} responde igual que en la mañana", cuerpo=caso["request"])
            if (e.status, e.response) != (caso["status"], caso["response"]):
                diferencias += 1
                tabla.add_row(
                    str(caso["n"]), str(e.id), caso["request"]["m"],
                    f"{caso['status']} {json.dumps(caso['response'], ensure_ascii=False)}",
                    f"{e.status} {json.dumps(e.response, ensure_ascii=False)}",
                )

    if diferencias:
        consola.print(tabla)
    color = "green" if not diferencias else "red"
    consola.print(f"[{color}]{len(casos) - diferencias}/{len(casos)} coinciden[/]")


@app.command()
def explorar(
    fase: Annotated[str, typer.Argument(help="http | integridad | control | comandos | memoria | todo")],
    max_requests: Annotated[int, typer.Option(help="Tope de requests de esta ejecución")] = 600,
):
    """Baterías automáticas de experimentos (cada request queda en el log)."""
    fases = {"http", "integridad", "control", "comandos", "memoria", "todo"}
    if fase not in fases:
        consola.print(f"[red]Fase desconocida. Opciones: {', '.join(sorted(fases))}[/]")
        raise typer.Exit(1)
    with Cliente(_config(), max_requests=max_requests) as c:
        x = Explorador(c)
        try:
            {"http": x.http, "integridad": x.integridad, "control": x.descubrir_control,
             "comandos": x.comandos, "memoria": x.memoria, "todo": x.todo}[fase]()
        except LimiteDeRequests as error:
            consola.print(f"[yellow]{error}[/]")
        consola.print(f"{c.enviados} requests enviados. Controles válidos hallados: {x.muestras_control}")


@app.command()
def concluir(id: int, texto: str):
    """Agrega o reemplaza la conclusión de una línea del log."""
    try:
        Bitacora(_config().log).concluir(id, texto)
    except KeyError as error:
        consola.print(f"[red]{error.args[0]}[/]")
        raise typer.Exit(1)
    consola.print(f"Conclusión guardada en la línea {id}")


@app.command()
def ver(
    ultimas: Annotated[int, typer.Option("--ultimas", "-n")] = 20,
    seq: Annotated[Optional[str], typer.Option(help="Solo esta secuencia, p. ej. s3")] = None,
):
    """Muestra las últimas líneas del log."""
    experimentos = Bitacora(_config().log).leer()
    if seq:
        experimentos = [e for e in experimentos if e.seq == seq]
    tabla = Table("id", "seq", "hipótesis", "request", "status", "response")
    for e in experimentos[-ultimas:]:
        pedido = e.request["m"] if isinstance(e.request, dict) and "m" in e.request else json.dumps(e.request, ensure_ascii=False)
        if e.ruta:
            pedido = f"{e.metodo} {e.ruta} {pedido if e.request is not None else ''}".strip()
        tabla.add_row(str(e.id), e.seq, e.hipotesis, pedido, str(e.status), json.dumps(e.response, ensure_ascii=False))
    consola.print(tabla)


if __name__ == "__main__":
    app()
