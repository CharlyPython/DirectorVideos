import json
from arquitecto.arquitecto import Arquitecto
from agentes.ilustrador import Ilustrador
from agentes.animador import Animador
from core.modelos import MAX_REGENERACIONES
from proveedores.base import RespuestaLLM
from proveedores.simulados import LLMSimulado
from tests.ayudas import proyecto_con_guion

async def test_planificar_respeta_usuario():
    plan, _ = await Arquitecto().planificar(LLMSimulado(), "Roma", 20, "épico", 80.0)
    assert (plan.duracion_min, plan.tono, plan.presupuesto_max) == (20, "épico", 80.0)
    assert plan.estilo_visual and plan.audiencia

async def test_revisar_guion_detecta_escena_corta_y_limita(raiz):
    ctx = await proyecto_con_guion(raiz)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[1].narracion = "muy corta"
    g.escenas[2].narracion = "corta también"; g.escenas[2].regeneraciones = MAX_REGENERACIONES
    ctx.almacen.guardar_guion(ctx.pid, g)
    ids = [i for i, _ in await Arquitecto().revisar_guion(ctx)]
    assert ids == [g.escenas[1].id]

async def test_revisar_imagenes_usa_supervisor(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx)
    class Exigente(LLMSimulado):
        async def evaluar_imagen(self, imagen, pregunta):
            return RespuestaLLM(json.dumps({"ok": imagen.stem != "c01_s001", "motivo": "incoherente"}), 0.01)
    ctx.proveedores.supervisor = Exigente()
    malas = await Arquitecto().revisar_imagenes(ctx, muestra=10)
    assert malas == [("c01_s001", "incoherente")]

async def test_revisar_clips_y_informe(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx); await Animador().ejecutar(ctx)
    assert await Arquitecto().revisar_clips(ctx) == []
    ruta = Arquitecto().informe(ctx)
    assert "Coste total" in ruta.read_text(encoding="utf-8")
