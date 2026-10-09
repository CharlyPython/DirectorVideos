import json
import pytest
from core.almacen import Almacen
from core.modelos import Plan
from director.contexto import Contexto
from director.eventos import Bus
from proveedores.base import RespuestaLLM
from proveedores.simulados import proveedores_simulados, LLMSimulado
from agentes.guionista import Guionista

def _ctx(raiz, duracion=2, llm=None):
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="Roma", duracion_min=duracion))
    prov = proveedores_simulados()
    if llm:
        prov.llm = llm
    return Contexto(a, prov, pid, Bus())

async def test_genera_5_escenas_por_minuto(raiz):
    ctx = _ctx(raiz, 3)
    r = await Guionista().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert r.ok and len(g.escenas) == 15
    assert len({e.id for e in g.escenas}) == 15
    assert g.escenas[0].id == "c01_s001"

class LLMEscenasCortas(LLMSimulado):
    """La primera vez que pide escenas devuelve una de menos."""
    def __init__(self): self.fallado = False
    async def completar(self, sistema, prompt, max_tokens=4000):
        r = await super().completar(sistema, prompt, max_tokens)
        if "TAREA: escenas" in prompt and not self.fallado:
            self.fallado = True
            d = json.loads(r.texto); d["escenas"] = d["escenas"][:-1]
            return RespuestaLLM(json.dumps(d), 0.0)
        return r

async def test_corrige_numero_de_escenas(raiz):
    ctx = _ctx(raiz, 1, LLMEscenasCortas())
    await Guionista().ejecutar(ctx)
    assert len(ctx.almacen.cargar_guion(ctx.pid).escenas) == 5

async def test_regenerar_escena_conserva_id_y_resetea_estado(raiz):
    ctx = _ctx(raiz, 1)
    gu = Guionista()
    await gu.ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[2].estado["imagen"] = "generado"
    ctx.almacen.guardar_guion(ctx.pid, g)
    await gu.regenerar_escena(ctx, "c01_s003")
    e = ctx.almacen.cargar_guion(ctx.pid).escena("c01_s003")
    assert e.narracion.startswith("nueva") and e.estado["imagen"] == "pendiente"

def test_reparto_de_escenas_por_capitulo():
    from agentes.guionista import repartir
    assert repartir([1.5, 1.5, 2], 25) == [8, 7, 10]
    assert sum(repartir([3, 3, 3], 50)) == 50
