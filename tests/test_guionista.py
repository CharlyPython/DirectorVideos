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


def test_repartir_suma_total_y_minimo_uno():
    from agentes.guionista import repartir
    r = repartir([1] * 12, 15)
    assert sum(r) == 15 and min(r) >= 1
    r = repartir([0.01, 5, 5], 10)
    assert sum(r) == 10 and min(r) >= 1


async def test_esquema_minutos_cero_reintenta(raiz):
    class LLMMinutosCero(LLMSimulado):
        def __init__(self): self.n = 0
        async def completar(self, sistema, prompt, max_tokens=4000):
            r = await super().completar(sistema, prompt, max_tokens)
            if "TAREA: esquema" in prompt:
                self.n += 1
                if self.n == 1:
                    d = json.loads(r.texto)
                    for c in d["capitulos"]:
                        c["minutos"] = 0
                    return RespuestaLLM(json.dumps(d), 0.0)
            return r
    llm = LLMMinutosCero()
    ctx = _ctx(raiz, 1, llm)
    await Guionista().ejecutar(ctx)
    assert llm.n == 2 and len(ctx.almacen.cargar_guion(ctx.pid).escenas) == 5


def test_reservar_y_liberar(raiz):
    from director.contexto import PresupuestoAgotado
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="x", duracion_min=1, presupuesto_max=1.0))
    ctx = Contexto(a, proveedores_simulados(), pid, Bus())
    ctx.reservar(0.6)
    with pytest.raises(PresupuestoAgotado):
        ctx.reservar(0.5)
    ctx.liberar(0.6)
    ctx.reservar(0.5)


async def test_requiere_ausente_persiste_error_y_emite(raiz):
    from agentes.base import procesar_escenas
    ctx = _ctx(raiz, 1)
    await Guionista().ejecutar(ctx)
    cola = ctx.bus.suscribir(ctx.pid)
    llamadas = []

    async def trabajo(e, g):
        llamadas.append(e.id); return 0.0
    r = await procesar_escenas(ctx, "t", "imagen", trabajo, requiere="audio")
    assert not r.ok and llamadas == [] and len(r.errores) == 5
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert all(e.estado["imagen"].value == "error" for e in g.escenas)
    assert cola.qsize() == 5


async def test_presupuesto_agotado_detiene_y_propaga(raiz):
    from agentes.base import procesar_escenas
    from director.contexto import PresupuestoAgotado
    ctx = _ctx(raiz, 1)
    await Guionista().ejecutar(ctx)
    ctx.concurrencia = 1
    p = ctx.plan
    p.presupuesto_max = ctx.almacen.coste_total(ctx.pid) + 1e-6  # una imagen cuesta más
    ctx.almacen.guardar_plan(ctx.pid, p)
    llamadas = []

    async def trabajo(e, g):
        llamadas.append(e.id); return 0.0
    with pytest.raises(PresupuestoAgotado):
        await procesar_escenas(ctx, "t", "imagen", trabajo)
    assert llamadas == []
