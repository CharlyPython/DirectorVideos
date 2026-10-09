import json
import logging
from contextlib import asynccontextmanager

from pydantic import ValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.almacen import Almacen
from core.config import Ajustes
from core.modelos import Fase
from director.director import Director
from director.eventos import Bus
from proveedores.base import Proveedores
from proveedores.fabrica import construir


FASES_PRODUCCION = (Fase.GUION, Fase.IMAGENES, Fase.CLIPS, Fase.AUDIO, Fase.MONTAJE, Fase.PUBLICACION)


def pausar_interrumpidos(almacen: Almacen) -> list[str]:
    """Tras un reinicio no queda ninguna tarea viva: pausa los proyectos que estaban a mitad de producción."""
    hechos = []
    for fila in almacen.listar():
        pid = fila["id"]
        if almacen.fase(pid) in FASES_PRODUCCION and not almacen.pausa(pid):
            almacen.pausar(pid, "Interrumpido por reinicio: pulsa Reanudar")
            hechos.append(pid)
    return hechos


def crear_app(ajustes: Ajustes | None = None, proveedores: Proveedores | None = None) -> FastAPI:
    ajustes = ajustes or Ajustes.desde_entorno()
    director = Director(Almacen(ajustes.raiz), proveedores or construir(ajustes), Bus(), ajustes.concurrencia)

    @asynccontextmanager
    async def _vida(_: FastAPI):
        pausar_interrumpidos(director.almacen)
        yield

    app = FastAPI(title="DirectorVideos", redirect_slashes=False, lifespan=_vida)
    app.state.ajustes = ajustes
    app.state.director = director

    @app.exception_handler(ValueError)
    async def _conflicto(_: Request, e: ValueError):
        if isinstance(e, (ValidationError, json.JSONDecodeError)):
            logging.exception("error interno")
            return JSONResponse({"detail": "error interno"}, status_code=500)
        logging.exception("conflicto")
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(KeyError)
    async def _no_existe(_: Request, e: KeyError):
        logging.exception("no existe")
        return JSONResponse({"detail": f"no existe: {e}"}, status_code=404)

    from app.api import router as api
    from app.web import router as web
    app.include_router(api)
    app.include_router(web)
    return app
