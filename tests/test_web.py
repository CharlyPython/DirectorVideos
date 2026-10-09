import asyncio
import httpx
from app.main import crear_app
from core.config import Ajustes
from tests.test_api import _esperar

async def test_paginas(raiz):
    app = crear_app(Ajustes(modo="simulado", raiz=raiz))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/")
        assert r.status_code == 200 and "Nueva idea" in r.text
        r = await c.post("/proyectos", data={"idea": "Roma antigua", "duracion_min": "1", "tono": "documental",
                                             "presupuesto_max": "20"}, follow_redirects=False)
        assert r.status_code == 303
        pid = r.headers["location"].rsplit("/", 1)[-1]
        await _esperar(c, pid, "aprobacion_guion")
        r = await c.get(f"/proyectos/{pid}")
        for texto in ("Guionista", "Ilustrador", "Animador", "Narrador", "Montador", "Publicador",
                      "Aprobar guion", "c01_s001"):
            assert texto in r.text
        assert (await c.get("/ajustes")).status_code == 200
