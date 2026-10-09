import asyncio

from agentes.animador import Animador
from agentes.guionista import Guionista
from agentes.ilustrador import Ilustrador
from agentes.montador import Montador
from agentes.narrador import Narrador
from agentes.publicador import Publicador
from arquitecto.arquitecto import Arquitecto
from core.almacen import Almacen
from core.costes import estimar
from core.modelos import CLAVES, Estado, Fase
from director.contexto import Contexto, PresupuestoAgotado
from director.eventos import Bus
from proveedores.base import Proveedores

DEPENDIENTES = {"guion": list(CLAVES), "imagen": ["imagen", "clip"], "clip": ["clip"], "audio": ["audio"]}
FASE_TRAS_REGENERAR = {"guion": Fase.IMAGENES, "imagen": Fase.CLIPS, "clip": Fase.MONTAJE, "audio": Fase.MONTAJE}


class Director:
    def __init__(self, almacen: Almacen, proveedores: Proveedores, bus: Bus, concurrencia: int = 6):
        self.almacen, self.proveedores, self.bus, self.concurrencia = almacen, proveedores, bus, concurrencia
        self.arquitecto = Arquitecto()
        self.guionista, self.ilustrador, self.animador = Guionista(), Ilustrador(), Animador()
        self.narrador, self.montador, self.publicador = Narrador(), Montador(), Publicador()
        self._tareas: dict[str, asyncio.Task] = {}

    def _ctx(self, pid: str) -> Contexto:
        return Contexto(self.almacen, self.proveedores, pid, self.bus, self.concurrencia)

    def _fase(self, ctx: Contexto, fase: Fase) -> None:
        self.almacen.set_fase(ctx.pid, fase)
        ctx.emitir("director", f"fase → {fase.value}", fase=fase.value)

    async def crear(self, idea: str, duracion_min: int, tono: str, presupuesto_max: float) -> str:
        plan, coste = await self.arquitecto.planificar(self.proveedores.supervisor, idea, duracion_min, tono,
                                                       presupuesto_max)
        pid = self.almacen.crear_proyecto(plan)
        self.almacen.registrar_coste(pid, "arquitecto", "plan", coste)
        return pid

    def estimacion(self, pid: str) -> dict:
        return estimar(self.almacen.cargar_plan(pid))

    # ---------- ciclo principal
    async def avanzar(self, pid: str) -> Fase:
        ctx = self._ctx(pid)
        try:
            while not self.almacen.pausa(pid):
                fase = self.almacen.fase(pid)
                if fase in (Fase.APROBACION_GUION, Fase.APROBACION_FINAL, Fase.COMPLETADO):
                    return fase
                siguiente = await self._paso(ctx, fase)
                if siguiente is None:
                    break
                self._fase(ctx, siguiente)
        except PresupuestoAgotado as e:
            self.almacen.pausar(pid, str(e))
            ctx.emitir("arquitecto", f"⏸ {e}. Sube el presupuesto y pulsa Reanudar.")
        except Exception as e:  # noqa: BLE001
            self.almacen.pausar(pid, f"error: {e}"[:500])
            ctx.emitir("director", f"❌ {e}")
        return self.almacen.fase(pid)

    async def _paso(self, ctx: Contexto, fase: Fase) -> Fase | None:
        a = self.arquitecto
        if fase == Fase.GUION:
            if not self.almacen.tiene_guion(ctx.pid):
                await self.guionista.ejecutar(ctx)
            for eid, motivo in await a.revisar_guion(ctx):
                a.marcar_regeneracion(ctx, [eid])
                await self.guionista.regenerar_escena(ctx, eid, motivo)
                ctx.emitir("arquitecto", f"reescrita {eid}: {motivo}")
            return Fase.APROBACION_GUION
        if fase == Fase.IMAGENES:
            return await self._produccion(ctx, self.ilustrador, a.revisar_imagenes, Fase.CLIPS)
        if fase == Fase.CLIPS:
            return await self._produccion(ctx, self.animador, a.revisar_clips, Fase.AUDIO)
        if fase == Fase.AUDIO:
            return await self._produccion(ctx, self.narrador, None, Fase.MONTAJE)
        if fase == Fase.MONTAJE:
            r = await self.montador.ejecutar(ctx)
            if not r.ok:
                self.almacen.pausar(ctx.pid, "; ".join(r.errores))
                return None
            await self.publicador.preparar(ctx)
            return Fase.APROBACION_FINAL
        if fase == Fase.PUBLICACION:
            r = await self.publicador.subir(ctx)
            if not r.ok:
                self.almacen.pausar(ctx.pid, "; ".join(r.errores))
                return None
            a.informe(ctx)
            return Fase.COMPLETADO
        raise ValueError(f"fase sin paso: {fase}")

    async def _produccion(self, ctx, agente, revisar, siguiente: Fase) -> Fase | None:
        r = await agente.ejecutar(ctx)
        if revisar and r.ok:
            malas = await revisar(ctx)
            if malas:
                ids = [i for i, _ in malas]
                self.arquitecto.marcar_regeneracion(ctx, ids)
                ctx.emitir("arquitecto", f"regenerar {len(ids)}: " + "; ".join(f"{i} ({m})" for i, m in malas))
                r = await agente.ejecutar(ctx, solo=ids)
        if not r.ok:
            self.almacen.pausar(ctx.pid, f"{agente.nombre}: {len(r.errores)} escenas con error — "
                                         + "; ".join(r.errores[:5]))
            return None
        return siguiente

    # ---------- control
    def ocupado(self, pid: str) -> bool:
        t = self._tareas.get(pid)
        return bool(t and not t.done())

    def lanzar(self, pid: str) -> None:
        if not self.ocupado(pid):
            self._tareas[pid] = asyncio.create_task(self.avanzar(pid))

    def _exigir(self, pid: str, fase: Fase) -> None:
        if self.almacen.fase(pid) != fase:
            raise ValueError(f"el proyecto está en {self.almacen.fase(pid).value}, no en {fase.value}")

    def aprobar_guion(self, pid: str) -> None:
        self._exigir(pid, Fase.APROBACION_GUION)
        self._fase(self._ctx(pid), Fase.IMAGENES)

    def aprobar_final(self, pid: str, titulo: str, miniatura: str, privacidad: str = "private",
                      publicar_en: str | None = None) -> None:
        self._exigir(pid, Fase.APROBACION_FINAL)
        d = self.almacen.cargar_json(pid, "publicacion.json")
        d.update(titulo_elegido=titulo, miniatura_elegida=miniatura, privacidad=privacidad, publicar_en=publicar_en)
        self.almacen.guardar_json(pid, "publicacion.json", d)
        self._fase(self._ctx(pid), Fase.PUBLICACION)

    def reanudar(self, pid: str) -> None:
        self.almacen.quitar_pausa(pid)
        self.lanzar(pid)

    def cambiar_presupuesto(self, pid: str, usd: float) -> None:
        plan = self.almacen.cargar_plan(pid)
        plan.presupuesto_max = float(usd)
        self.almacen.guardar_plan(pid, plan)

    async def regenerar(self, pid: str, escena_id: str, clave: str) -> None:
        if clave not in DEPENDIENTES:
            raise ValueError(f"clave desconocida: {clave}")
        if self.ocupado(pid):
            raise ValueError("el proyecto está trabajando; espera a que termine")
        fase = self.almacen.fase(pid)
        if fase in (Fase.PUBLICACION, Fase.COMPLETADO):
            raise ValueError("el vídeo ya está publicado o publicándose; no se puede regenerar")
        if fase in (Fase.GUION, Fase.APROBACION_GUION) and clave != "guion":
            raise ValueError("aprueba el guion antes de regenerar imágenes, clips o audio")
        g = self.almacen.cargar_guion(pid)
        try:
            e = g.escena(escena_id)
        except KeyError:
            raise ValueError(f"escena desconocida: {escena_id}") from None
        self._tareas[pid] = asyncio.current_task()
        ctx = self._ctx(pid)
        try:
            for k in DEPENDIENTES[clave]:
                e.estado[k] = Estado.PENDIENTE
            self.almacen.guardar_guion(pid, g)
            if clave == "guion":
                await self.guionista.regenerar_escena(ctx, escena_id, "petición del usuario")
            else:
                agente = {"imagen": self.ilustrador, "clip": self.animador, "audio": self.narrador}[clave]
                await agente.ejecutar(ctx, solo=[escena_id])
        except PresupuestoAgotado as ex:
            self.almacen.pausar(pid, str(ex))
            ctx.emitir("arquitecto", f"⏸ {ex}. Sube el presupuesto y pulsa Reanudar.")
        finally:
            self._tareas.pop(pid, None)
            destino, orden = FASE_TRAS_REGENERAR[clave], list(Fase)
            if orden.index(self.almacen.fase(pid)) > orden.index(destino):
                self._fase(ctx, destino)

    async def regenerar_capitulo(self, pid: str, numero: int) -> None:
        self._exigir(pid, Fase.APROBACION_GUION)
        if self.ocupado(pid):
            raise ValueError("el proyecto está trabajando; espera a que termine")
        self._tareas[pid] = asyncio.current_task()
        try:
            await self.guionista.regenerar_capitulo(self._ctx(pid), numero)
        finally:
            self._tareas.pop(pid, None)
