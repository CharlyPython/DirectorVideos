from core.almacen import Almacen
from core.modelos import Plan
from director.contexto import Contexto
from director.eventos import Bus
from proveedores.simulados import proveedores_simulados
from agentes.guionista import Guionista


async def proyecto_con_guion(raiz, duracion=1, presupuesto=50.0) -> Contexto:
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="Roma", duracion_min=duracion, presupuesto_max=presupuesto))
    ctx = Contexto(a, proveedores_simulados(), pid, Bus())
    await Guionista().ejecutar(ctx)
    return ctx
