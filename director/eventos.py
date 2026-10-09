import asyncio
from collections import defaultdict


class Bus:
    def __init__(self):
        self._colas: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def suscribir(self, pid: str) -> asyncio.Queue:
        cola: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._colas[pid].add(cola)
        return cola

    def desuscribir(self, pid: str, cola: asyncio.Queue) -> None:
        self._colas[pid].discard(cola)

    def emitir(self, pid: str, evento: dict) -> None:
        for cola in list(self._colas[pid]):
            if not cola.full():
                cola.put_nowait(evento)
