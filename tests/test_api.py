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
    assert (await cliente.get(f"/media/{pid}/../director.db")).status_code == 404
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
    assert (await cliente.get(f"/media/{pid}/%2e%2e/director.db")).status_code == 404
    assert (await cliente.get(f"/media/{pid}/")).status_code == 404


async def test_media_pid_invalido_y_raw(cliente):
    for ruta in ("/media/./director.db", "/media/%2e/director.db", "/media/%2e%2e/x", "/media/../director.db"):
        assert (await cliente.get(ruta)).status_code == 404
    escala = {"type": "http", "method": "GET", "path": "/media/./director.db", "raw_path": b"/media/./director.db",
              "query_string": b"", "headers": [], "http_version": "1.1", "scheme": "http",
              "server": ("t", 80), "client": ("c", 1)}
    msgs = []

    async def recibir():
        return {"type": "http.request", "body": b""}

    async def enviar(m):
        msgs.append(m)
    await cliente.app(escala, recibir, enviar)
    assert msgs[0]["status"] == 404


async def test_presupuesto_y_sse_404(cliente):
    assert (await cliente.post("/api/proyectos/nope/presupuesto", json={"usd": 5})).status_code == 404
    assert (await cliente.get("/api/proyectos/nope/eventos")).status_code == 404
    r = await cliente.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1})
    pid = r.json()["id"]
    assert (await cliente.post(f"/api/proyectos/{pid}/presupuesto", json={"usd": -1})).status_code == 422
    assert (await cliente.post(f"/api/proyectos/{pid}/presupuesto", json={})).status_code == 422


async def test_regenerar_desde_aprobacion_final_relanza(cliente):
    r = await cliente.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1, "presupuesto_max": 50})
    pid = r.json()["id"]
    d = await _esperar(cliente, pid, "aprobacion_guion")
    await cliente.post(f"/api/proyectos/{pid}/aprobar-guion")
    d = await _esperar(cliente, pid, "aprobacion_final")
    eid = d["guion"]["escenas"][0]["id"]
    r = await cliente.post(f"/api/proyectos/{pid}/escenas/{eid}/regenerar/imagen")
    assert r.status_code == 200
    d = await _esperar(cliente, pid, "aprobacion_final")
    assert d["pausa"] is None


async def test_reintentar_subida_limpia_marca(cliente):
    r = await cliente.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1, "presupuesto_max": 50})
    pid = r.json()["id"]
    await _esperar(cliente, pid, "aprobacion_guion")
    await cliente.post(f"/api/proyectos/{pid}/aprobar-guion")
    d = await _esperar(cliente, pid, "aprobacion_final")
    assert (await cliente.post(f"/api/proyectos/{pid}/reintentar-subida")).status_code == 409   # no pausado
    a = cliente.app.state.director.almacen
    pub = a.cargar_json(pid, "publicacion.json")
    pub.update(titulo_elegido=pub["titulos"][0], miniatura_elegida=pub["miniaturas"][0], subida_iniciada="2026-01-01T00:00:00")
    a.guardar_json(pid, "publicacion.json", pub)
    a.set_fase(pid, __import__("core.modelos", fromlist=["Fase"]).Fase.PUBLICACION)
    a.pausar(pid, "Una subida anterior se interrumpió")
    assert (await cliente.post(f"/api/proyectos/{pid}/reintentar-subida")).status_code == 200
    d = await _esperar(cliente, pid, "completado")
    assert "subida_iniciada" not in d["publicacion"] and d["publicacion"]["video_id"]
