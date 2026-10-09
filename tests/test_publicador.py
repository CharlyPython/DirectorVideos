# tests/test_publicador.py
import pytest
from PIL import Image
from agentes.publicador import Publicador, marcas_capitulos
from tests.test_montador import _producido
from agentes.montador import Montador

def test_marcas_capitulos():
    t = marcas_capitulos([{"titulo": "Inicio", "inicio": 0}, {"titulo": "Caída", "inicio": 3725.2}])
    assert t == "00:00 Inicio\n1:02:05 Caída"

async def test_preparar_y_subir(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    pub = Publicador()
    r = await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    assert r.ok and len(d["titulos"]) == 3 and len(d["miniaturas"]) == 3
    assert "00:00" in d["descripcion"]
    assert Image.open(ctx.almacen.ruta(ctx.pid) / d["miniaturas"][0]).size == (1280, 720)
    r = await pub.subir(ctx)
    assert not r.ok                                   # falta elección
    d["titulo_elegido"], d["miniatura_elegida"] = d["titulos"][1], d["miniaturas"][2]
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    r = await pub.subir(ctx)
    sub = ctx.proveedores.subidor.subidas[0]
    assert r.ok and sub["meta"]["titulo"] == d["titulos"][1]
    assert ctx.almacen.cargar_json(ctx.pid, "publicacion.json")["video_id"] == "SIMULADO123"
