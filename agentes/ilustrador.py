from agentes.base import Resultado, procesar_escenas
from director.contexto import Contexto


class Ilustrador:
    nombre = "ilustrador"

    async def ejecutar(self, ctx: Contexto, solo: list[str] | None = None) -> Resultado:
        async def trabajo(e, guion):
            prompt = f"{e.imagen_prompt}. Visual style: {guion.biblia_visual}"
            return await ctx.proveedores.imagen.generar(prompt, ctx.almacen.archivo(ctx.pid, "imagen", e.id))
        return await procesar_escenas(ctx, self.nombre, "imagen", trabajo, solo)
