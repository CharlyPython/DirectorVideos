from agentes.base import Resultado, procesar_escenas
from director.contexto import Contexto
from herramientas.ffmpeg import duracion
from herramientas.reintentos import ErrorPermanente


class Narrador:
    nombre = "narrador"

    async def ejecutar(self, ctx: Contexto, solo: list[str] | None = None) -> Resultado:
        async def trabajo(e, guion):
            if not e.narracion.strip():
                raise ErrorPermanente("narración vacía")
            destino = ctx.almacen.archivo(ctx.pid, "audio", e.id)
            coste = await ctx.proveedores.tts.sintetizar(e.narracion, destino)
            e.duracion_audio = await duracion(destino)
            return coste
        return await procesar_escenas(ctx, self.nombre, "audio", trabajo, solo)
