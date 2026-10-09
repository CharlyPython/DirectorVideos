import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.modelos import Estado, Fase

router = APIRouter()
EDITABLES = {Fase.APROBACION_GUION, Fase.APROBACION_FINAL}


class NuevoProyecto(BaseModel):
    idea: str = Field(min_length=3)
    duracion_min: int = Field(ge=1, le=50)
    tono: str = "documental"
    presupuesto_max: float = Field(gt=0, default=50.0)


class Aprobacion(BaseModel):
    titulo: str
    miniatura: str
    privacidad: Literal["private", "unlisted", "public"] = "private"
    publicar_en: str | None = None


class Presupuesto(BaseModel):
    usd: float = Field(gt=0, allow_inf_nan=False)


class EdicionEscena(BaseModel):
    narracion: str | None = None
    imagen_prompt: str | None = None
    movimiento_prompt: str | None = None


def _d(req: Request):
    return req.app.state.director


def detalle(director, pid: str) -> dict:
    a = director.almacen
    fase = a.fase(pid)
    return {"id": pid, "plan": a.cargar_plan(pid).model_dump(), "fase": fase.value, "pausa": a.pausa(pid),
            "coste": round(a.coste_total(pid), 2), "costes": a.costes_por_agente(pid),
            "estimacion": director.estimacion(pid),
            "guion": a.cargar_guion(pid).model_dump() if a.tiene_guion(pid) else None,
            "montaje": a.cargar_json(pid, "montaje.json"), "publicacion": a.cargar_json(pid, "publicacion.json"),
            "ocupado": director.ocupado(pid), "logs": a.logs(pid, 50)}


@router.get("/api/proyectos")
async def listar(req: Request):
    return _d(req).almacen.listar()


@router.post("/api/proyectos")
async def crear(req: Request, datos: NuevoProyecto):
    d = _d(req)
    pid = await d.crear(datos.idea, datos.duracion_min, datos.tono, datos.presupuesto_max)
    d.lanzar(pid)
    return {"id": pid}


@router.get("/api/proyectos/{pid}")
async def ver(req: Request, pid: str):
    return detalle(_d(req), pid)


@router.post("/api/proyectos/{pid}/aprobar-guion")
async def aprobar_guion(req: Request, pid: str):
    d = _d(req); d.aprobar_guion(pid); d.lanzar(pid)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/aprobar-final")
async def aprobar_final(req: Request, pid: str, datos: Aprobacion):
    d = _d(req); d.aprobar_final(pid, datos.titulo, datos.miniatura, datos.privacidad, datos.publicar_en or None)
    d.lanzar(pid)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/reanudar")
async def reanudar(req: Request, pid: str):
    _d(req).reanudar(pid)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/presupuesto")
async def presupuesto(req: Request, pid: str, datos: Presupuesto):
    d = _d(req)
    d.almacen.fase(pid)
    d.cambiar_presupuesto(pid, datos.usd)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/escenas/{eid}")
async def editar_escena(req: Request, pid: str, eid: str, datos: EdicionEscena):
    d = _d(req)
    if d.almacen.fase(pid) not in EDITABLES or d.ocupado(pid):
        raise ValueError("solo se puede editar en los puntos de aprobación")
    g = d.almacen.cargar_guion(pid)
    e = g.escena(eid)
    if not datos.model_fields_set & {"narracion", "imagen_prompt", "movimiento_prompt"}:
        return e.model_dump()
    if datos.narracion is not None:
        e.narracion, e.estado["audio"] = datos.narracion, Estado.PENDIENTE
    if datos.imagen_prompt is not None:
        e.imagen_prompt = datos.imagen_prompt
        e.estado["imagen"] = e.estado["clip"] = Estado.PENDIENTE
    if datos.movimiento_prompt is not None:
        e.movimiento_prompt, e.estado["clip"] = datos.movimiento_prompt, Estado.PENDIENTE
    d.almacen.guardar_guion(pid, g)
    if d.almacen.fase(pid) == Fase.APROBACION_FINAL:
        afectadas = []
        if datos.imagen_prompt is not None:
            afectadas.append(Fase.IMAGENES)
        if datos.movimiento_prompt is not None:
            afectadas.append(Fase.CLIPS)
        if datos.narracion is not None:
            afectadas.append(Fase.AUDIO)
        if afectadas:
            orden = [Fase.IMAGENES, Fase.CLIPS, Fase.AUDIO]
            d.almacen.set_fase(pid, min(afectadas, key=orden.index))   # el Director salta lo ya generado
            d.lanzar(pid)
    return e.model_dump()


@router.post("/api/proyectos/{pid}/escenas/{eid}/regenerar/{clave}")
async def regenerar(req: Request, pid: str, eid: str, clave: str):
    if clave not in ("guion", "imagen", "clip", "audio"):
        raise HTTPException(400, "clave inválida")
    await _d(req).regenerar(pid, eid, clave)
    return _d(req).almacen.cargar_guion(pid).escena(eid).model_dump()


@router.post("/api/proyectos/{pid}/capitulos/{numero}/regenerar")
async def regenerar_capitulo(req: Request, pid: str, numero: int):
    await _d(req).regenerar_capitulo(pid, numero)
    return {"ok": True}


@router.get("/api/proyectos/{pid}/eventos")
async def eventos(req: Request, pid: str):
    d = _d(req)
    d.almacen.fase(pid)
    bus = d.bus
    cola = bus.suscribir(pid)

    async def flujo():
        try:
            while not await req.is_disconnected():
                try:
                    ev = await asyncio.wait_for(cola.get(), timeout=15)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.desuscribir(pid, cola)
    return StreamingResponse(flujo(), media_type="text/event-stream")


@router.get("/media/{pid}/{ruta:path}")
async def media(req: Request, pid: str, ruta: str):
    a = _d(req).almacen
    try:
        a.fase(pid)
        base = a.ruta(pid).resolve()
        if base.parent != a.raiz.resolve():
            raise HTTPException(404)
        destino = (base / ruta).resolve()
        if base not in destino.parents or not destino.is_file():
            raise HTTPException(404)
    except (OSError, ValueError, KeyError):
        raise HTTPException(404)
    return FileResponse(destino)
