from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.almacen import Almacen
from core.config import Ajustes
from director.director import Director
from director.eventos import Bus
from proveedores.base import Proveedores
from proveedores.fabrica import construir


def crear_app(ajustes: Ajustes | None = None, proveedores: Proveedores | None = None) -> FastAPI:
    ajustes = ajustes or Ajustes.desde_entorno()
    app = FastAPI(title="DirectorVideos", redirect_slashes=False)
    app.state.ajustes = ajustes
    app.state.director = Director(Almacen(ajustes.raiz), proveedores or construir(ajustes), Bus(),
                                  ajustes.concurrencia)

    @app.exception_handler(ValueError)
    async def _conflicto(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(KeyError)
    async def _no_existe(_: Request, e: KeyError):
        return JSONResponse({"detail": f"no existe: {e}"}, status_code=404)

    from app.api import router as api
    from app.web import router as web
    app.include_router(api)
    app.include_router(web)
    return app
