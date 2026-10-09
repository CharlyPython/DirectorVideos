from agentes.narrador import Narrador
from tests.ayudas import proyecto_con_guion


async def test_narra_y_mide_duracion(raiz):
    ctx = await proyecto_con_guion(raiz)
    r = await Narrador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert r.ok
    assert all(abs(e.duracion_audio - 12) < 0.4 for e in g.escenas)


async def test_narracion_vacia_es_error_sin_llamada(raiz):
    ctx = await proyecto_con_guion(raiz)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[0].narracion = "  "
    ctx.almacen.guardar_guion(ctx.pid, g)
    r = await Narrador().ejecutar(ctx)
    assert len(r.errores) == 1 and "vacía" in r.errores[0]
