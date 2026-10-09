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


async def test_revision_final_y_pausa(raiz):
    app = crear_app(Ajustes(modo="simulado", raiz=raiz))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        pid = (await c.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1})).json()["id"]
        await _esperar(c, pid, "aprobacion_guion")
        await c.post(f"/api/proyectos/{pid}/aprobar-guion")
        await _esperar(c, pid, "aprobacion_final")
        for ruta in (f"/proyectos/{pid}", f"/proyectos/{pid}/parcial"):
            r = await c.get(ruta)
            assert r.status_code == 200
        assert "Revisión final" in (await c.get(f"/proyectos/{pid}")).text
        app.state.director.almacen.pausar(pid, "x")
        r = await c.get(f"/proyectos/{pid}/parcial")
        assert "Pausado" in r.text and "Reanudar" in r.text
        r = await c.get(f"/proyectos/{pid}")
        assert "Pausado" in r.text and "Reanudar" in r.text
