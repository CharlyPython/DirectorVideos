from agentes.base import Resultado, procesar_escenas
from core.modelos import SEGUNDOS_CLIP
from director.contexto import Contexto


class Animador:
    nombre = "animador"

    async def ejecutar(self, ctx: Contexto, solo: list[str] | None = None) -> Resultado:
        async def trabajo(e, guion):
            return await ctx.proveedores.video.animar(
                ctx.almacen.archivo(ctx.pid, "imagen", e.id), e.movimiento_prompt,
                ctx.almacen.archivo(ctx.pid, "clip", e.id), SEGUNDOS_CLIP)
        return await procesar_escenas(ctx, self.nombre, "clip", trabajo, solo, requiere="imagen")
