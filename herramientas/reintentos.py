import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class ErrorTransitorio(Exception):
    """Red, 429, 5xx: merece reintento."""


class ErrorPermanente(Exception):
    """Petición inválida, contenido rechazado: no reintentar."""


async def con_reintentos(fn: Callable[[], Awaitable[T]], intentos: int = 3, base: float = 2.0) -> T:
    for i in range(intentos):
        try:
            return await fn()
        except ErrorTransitorio:
            if i == intentos - 1:
                raise
            await asyncio.sleep(base * (2 ** i))
    raise AssertionError("inalcanzable")
