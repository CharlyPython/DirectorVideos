import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api import detalle
from core.costes import PRECIOS

router = APIRouter()
plantillas = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
AGENTES = [("guionista", "Guionista", ["guion"]), ("ilustrador", "Ilustrador", ["imagenes"]),
           ("animador", "Animador", ["clips"]), ("narrador", "Narrador", ["audio"]),
           ("montador", "Montador", ["montaje"]), ("publicador", "Publicador", ["publicacion"])]
ORDEN = ["guion", "aprobacion_guion", "imagenes", "clips", "audio", "montaje", "aprobacion_final",
         "publicacion", "completado"]


def estado_agente(fase: str, pausa: str | None, fases_agente: list[str]) -> str:
    i_fase, i_ag = ORDEN.index(fase), ORDEN.index(fases_agente[0])
    if i_fase > i_ag:
        return "hecho"
    if i_fase == i_ag:
        return "error" if pausa else "trabajando"
    if fase in ("aprobacion_guion", "aprobacion_final") and ORDEN.index(fase) + 1 == i_ag:
        return "esperando"
    return "cola"


def _ctx(req: Request, pid: str) -> dict:
    d = req.app.state.director
    det = detalle(d, pid)
    det["agentes"] = [(clave, nombre, estado_agente(det["fase"], det["pausa"], fases))
                      for clave, nombre, fases in AGENTES]
    return {"request": req, "p": det}


@router.get("/", response_class=HTMLResponse)
async def panel(req: Request):
    a = req.app.state.director.almacen
    hoy = datetime.now()
    return plantillas.TemplateResponse(req, "panel.html", {
        "proyectos": a.listar(), "coste_mes": a.coste_mes(hoy.year, hoy.month),
        "modo": req.app.state.ajustes.modo})


@router.post("/proyectos")
async def crear(req: Request, idea: str = Form(...), duracion_min: int = Form(...), tono: str = Form("documental"),
                presupuesto_max: float = Form(50.0)):
    d = req.app.state.director
    pid = await d.crear(idea, duracion_min, tono, presupuesto_max)
    d.lanzar(pid)
    return RedirectResponse(f"/proyectos/{pid}", status_code=303)


@router.get("/proyectos/{pid}", response_class=HTMLResponse)
async def proyecto(req: Request, pid: str):
    return plantillas.TemplateResponse(req, "proyecto.html", _ctx(req, pid))


@router.get("/proyectos/{pid}/parcial", response_class=HTMLResponse)
async def parcial(req: Request, pid: str):
    return plantillas.TemplateResponse(req, "_timeline.html", _ctx(req, pid))


@router.get("/ajustes", response_class=HTMLResponse)
async def ajustes(req: Request):
    from proveedores.fabrica import TOKEN_YOUTUBE
    from proveedores.youtube import youtube_conectado
    aj = req.app.state.ajustes
    return plantillas.TemplateResponse(req, "ajustes.html", {
        "aj": aj, "precios": PRECIOS, "youtube": youtube_conectado(TOKEN_YOUTUBE),
        "claves": {"Anthropic": bool(aj.anthropic_key), "fal.ai": bool(aj.fal_key),
                   "ElevenLabs": bool(aj.elevenlabs_key), "OpenAI": bool(aj.openai_key)}})


@router.post("/ajustes/youtube")
async def conectar(req: Request):
    from proveedores.fabrica import TOKEN_YOUTUBE
    from proveedores.youtube import conectar_youtube
    asyncio.create_task(asyncio.to_thread(conectar_youtube, req.app.state.ajustes.youtube_client_secret,
                                          TOKEN_YOUTUBE))
    return RedirectResponse("/ajustes", status_code=303)
