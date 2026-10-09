import asyncio
import httpx
import pytest
from app.main import crear_app
from core.config import Ajustes

@pytest.fixture
async def cliente(raiz):
    app = crear_app(Ajustes(modo="simulado", raiz=raiz))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c

async def _esperar(c, pid, fase):
    for _ in range(600):
        d = (await c.get(f"/api/proyectos/{pid}")).json()
        if d["fase"] == fase and not d["ocupado"]:
            return d
        await asyncio.sleep(0.1)
    raise AssertionError(d)

async def test_flujo_por_api(cliente):
    r = await cliente.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1, "tono": "documental",
                                                   "presupuesto_max": 50})
    pid = r.json()["id"]
    d = await _esperar(cliente, pid, "aprobacion_guion")
    assert len(d["guion"]["escenas"]) == 5 and d["estimacion"]["total"] >= 0
    eid = d["guion"]["escenas"][0]["id"]
    r = await cliente.post(f"/api/proyectos/{pid}/escenas/{eid}", json={"narracion": "texto editado " * 5})
    assert r.status_code == 200
    assert (await cliente.post(f"/api/proyectos/{pid}/aprobar-final", json={"titulo": "x", "miniatura": "y"})).status_code == 409
    await cliente.post(f"/api/proyectos/{pid}/aprobar-guion")
    d = await _esperar(cliente, pid, "aprobacion_final")
    m = await cliente.get(f"/media/{pid}/final.mp4")
    assert m.status_code == 200
    assert (await cliente.get(f"/media/{pid}/../director.db")).status_code in (400, 404)
    pub = d["publicacion"]
    await cliente.post(f"/api/proyectos/{pid}/aprobar-final",
                       json={"titulo": pub["titulos"][0], "miniatura": pub["miniaturas"][0]})
    await _esperar(cliente, pid, "completado")

async def test_404(cliente):
    assert (await cliente.get("/api/proyectos/nope")).status_code == 404


async def test_media_bloquea_traversal(cliente):
    r = await cliente.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1})
    pid = r.json()["id"]
    await _esperar(cliente, pid, "aprobacion_guion")
    assert (await cliente.get(f"/media/{pid}/%2e%2e/director.db")).status_code in (400, 404)
    assert (await cliente.get(f"/media/{pid}/")).status_code == 404
