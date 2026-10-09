from core.modelos import Estado
from agentes.ilustrador import Ilustrador
from agentes.animador import Animador
from tests.ayudas import proyecto_con_guion


class ContadorImagen:
    def __init__(self, interno):
        self.interno, self.prompts = interno, []

    async def generar(self, prompt, destino):
        self.prompts.append(prompt)
        return await self.interno.generar(prompt, destino)


async def test_ilustra_todas_con_biblia(raiz):
    ctx = await proyecto_con_guion(raiz)
    cont = ContadorImagen(ctx.proveedores.imagen)
    ctx.proveedores.imagen = cont
    r = await Ilustrador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert r.ok and len(cont.prompts) == 5
    assert all(g.biblia_visual in p for p in cont.prompts)
    assert all(e.estado["imagen"] == Estado.GENERADO for e in g.escenas)


async def test_reanuda_sin_repetir_y_repara_faltantes(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx)
    ctx.almacen.archivo(ctx.pid, "imagen", "c01_s002").unlink()
    cont = ContadorImagen(ctx.proveedores.imagen)
    ctx.proveedores.imagen = cont
    await Ilustrador().ejecutar(ctx)
    assert len(cont.prompts) == 1


async def test_animador_requiere_imagen(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx, solo=["c01_s001"])
    r = await Animador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert g.escena("c01_s001").estado["clip"] == Estado.GENERADO
    assert g.escena("c01_s002").estado["clip"] == Estado.ERROR
    assert not r.ok and len(r.errores) == 4


async def test_error_en_una_escena_no_para_el_resto(raiz):
    ctx = await proyecto_con_guion(raiz)
    interno = ctx.proveedores.imagen

    class Rompe:
        async def generar(self, prompt, destino):
            if destino.stem == "c01_s003":
                raise ValueError("contenido rechazado")
            return await interno.generar(prompt, destino)

    ctx.proveedores.imagen = Rompe()
    r = await Ilustrador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert len(r.errores) == 1 and "rechazado" in g.escena("c01_s003").error
    assert sum(e.estado["imagen"] == Estado.GENERADO for e in g.escenas) == 4
