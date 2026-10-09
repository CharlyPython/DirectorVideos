import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from core.costes import precio_unitario
from core.modelos import Escena, Estado, Guion
from director.contexto import Contexto, PresupuestoAgotado
from herramientas.reintentos import con_reintentos


@dataclass
class Resultado:
    ok: bool
    errores: list[str] = field(default_factory=list)
    coste: float = 0.0


def _necesita(ctx: Contexto, e: Escena, clave: str) -> bool:
    return e.estado[clave] != Estado.GENERADO or not ctx.almacen.archivo(ctx.pid, clave, e.id).exists()


async def procesar_escenas(ctx: Contexto, agente: str, clave: str,
                           trabajo: Callable[[Escena, Guion], Awaitable[float]],
                           solo: list[str] | None = None, requiere: str | None = None) -> Resultado:
    guion = ctx.almacen.cargar_guion(ctx.pid)
    objetivo = [e for e in guion.escenas if (e.id in solo if solo else _necesita(ctx, e, clave))]
    estimado = precio_unitario(clave, ctx.plan)
    sem = asyncio.Semaphore(ctx.concurrencia)
    res = Resultado(ok=True)
    hechas = 0

    async def una(e: Escena) -> None:
        nonlocal hechas
        async with sem:
            if requiere and not ctx.almacen.archivo(ctx.pid, requiere, e.id).exists():
                e.estado[clave], e.error = Estado.ERROR, f"falta {requiere}"
                res.errores.append(f"{e.id}: falta {requiere}")
                return
            ctx.reservar(estimado)
            try:
                coste = await con_reintentos(lambda: trabajo(e, guion))
                ctx.cobrar(agente, e.id, coste)
                res.coste += coste
                e.estado[clave], e.error = Estado.GENERADO, None
            except Exception as ex:  # noqa: BLE001 — se registra por escena y se sigue
                e.estado[clave], e.error = Estado.ERROR, str(ex)[:300]
                res.errores.append(f"{e.id}: {ex}")
            finally:
                ctx.liberar(estimado)
                ctx.almacen.guardar_guion(ctx.pid, guion)
                hechas += 1
                ctx.emitir(agente, f"{e.id} {e.estado[clave].value}", hechas=hechas, total=len(objetivo))

    resultados = await asyncio.gather(*(una(e) for e in objetivo), return_exceptions=True)
    for r in resultados:
        if isinstance(r, PresupuestoAgotado):
            raise r
        if isinstance(r, BaseException):
            raise r
    res.ok = not res.errores
    return res
