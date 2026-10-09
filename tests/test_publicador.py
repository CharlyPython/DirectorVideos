# tests/test_publicador.py
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


async def test_no_sube_dos_veces(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    pub = Publicador()
    await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    d["titulo_elegido"], d["miniatura_elegida"] = d["titulos"][0], d["miniaturas"][0]
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    assert (await pub.subir(ctx)).ok
    r = await pub.subir(ctx)
    assert r.ok and len(ctx.proveedores.subidor.subidas) == 1


async def test_miniatura_fuera_de_lista_no_sube(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    pub = Publicador()
    await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    d["titulo_elegido"], d["miniatura_elegida"] = d["titulos"][0], "no_existe.png"
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    r = await pub.subir(ctx)
    assert not r.ok and r.errores and not ctx.proveedores.subidor.subidas


async def test_preparar_conserva_video_id(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    pub = Publicador()
    await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    d["video_id"] = "ABC"
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    await pub.preparar(ctx)
    assert ctx.almacen.cargar_json(ctx.pid, "publicacion.json")["video_id"] == "ABC"


async def test_preparar_no_repite_gasto_y_refresca_capitulos(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    llm, img = ctx.proveedores.llm, ctx.proveedores.imagen
    n = {"llm": 0, "img": 0}
    c_llm, c_img = llm.completar, img.generar

    async def f_llm(*a, **k):
        n["llm"] += 1
        return await c_llm(*a, **k)

    async def f_img(*a, **k):
        n["img"] += 1
        return await c_img(*a, **k)
    llm.completar, img.generar = f_llm, f_img
    pub = Publicador()
    await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    d["titulos"][0] = "Editado"
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    m = ctx.almacen.cargar_json(ctx.pid, "montaje.json")
    m["capitulos"][0]["titulo"] = "Nuevo cap"
    ctx.almacen.guardar_json(ctx.pid, "montaje.json", m)
    antes = (n["llm"], n["img"])
    await pub.preparar(ctx)
    d2 = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    assert (n["llm"], n["img"]) == antes == (1, 3)
    assert d2["titulos"][0] == "Editado" and "Nuevo cap" in d2["descripcion"]


async def test_subida_interrumpida_no_resube(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    pub = Publicador()
    await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    d["titulo_elegido"], d["miniatura_elegida"] = d["titulos"][0], d["miniaturas"][0]
    d["subida_iniciada"] = "2026-01-01T00:00:00"
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    r = await pub.subir(ctx)
    assert not r.ok and "subida anterior" in r.errores[0] and not ctx.proveedores.subidor.subidas
    d.pop("subida_iniciada")
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    assert (await pub.subir(ctx)).ok
    assert "subida_iniciada" not in ctx.almacen.cargar_json(ctx.pid, "publicacion.json")


async def test_miniaturas_sin_presupuesto_pausan(raiz):
    import pytest
    from director.contexto import PresupuestoAgotado
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    plan = ctx.plan
    plan.presupuesto_max = ctx.almacen.coste_total(ctx.pid) + 0.04   # cabe el LLM (0,05)? no
    ctx.almacen.guardar_plan(ctx.pid, plan)
    with pytest.raises(PresupuestoAgotado):
        await Publicador().preparar(ctx)
