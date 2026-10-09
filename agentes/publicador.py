# agentes/publicador.py
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agentes.base import Resultado
from core.costes import PRECIOS
from director.contexto import Contexto
from herramientas.reintentos import con_reintentos
from proveedores.base import armar_prompt, completar_json

SISTEMA = "Eres experto en SEO y CTR de YouTube en español. Respondes SOLO con JSON válido."


def _hms(t: float) -> str:
    t = int(t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def marcas_capitulos(capitulos: list[dict]) -> str:
    return "\n".join(f"{_hms(c['inicio'])} {c['titulo']}" for c in capitulos)


def _rotular(ruta: Path, texto: str) -> None:
    img = Image.open(ruta).convert("RGB").resize((1280, 720))
    d = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("arialbd.ttf", 96)
    except OSError:
        fuente = ImageFont.load_default()
    x, y = 60, 720 - 200
    d.text((x, y), texto.upper(), font=fuente, fill="white", stroke_width=8, stroke_fill="black")
    img.save(ruta)


EST_METADATOS = 0.05


class Publicador:
    nombre = "publicador"

    async def preparar(self, ctx: Contexto) -> Resultado:
        guion, plan = ctx.almacen.cargar_guion(ctx.pid), ctx.plan
        montaje = ctx.almacen.cargar_json(ctx.pid, "montaje.json")
        base = ctx.almacen.ruta(ctx.pid)
        previo = ctx.almacen.cargar_json(ctx.pid, "publicacion.json") or {}
        if (len(previo.get("titulos") or []) == 3 and len(previo.get("miniaturas") or []) == 3
                and all((base / m).exists() for m in previo["miniaturas"])):
            # Ya preparado (re-montaje): solo se refrescan las marcas de capítulos; sin gasto ni pérdida de elecciones.
            desc = previo.get("descripcion", "").split("\n\nCapítulos:\n")[0]
            previo["descripcion"] = f"{desc}\n\nCapítulos:\n{marcas_capitulos(montaje['capitulos'])}"
            ctx.almacen.guardar_json(ctx.pid, "publicacion.json", previo)
            ctx.emitir(self.nombre, "metadatos y miniaturas ya preparados; capítulos actualizados")
            return Resultado(ok=True)

        def validar(d):
            if len(d["titulos"]) != 3 or len(d["miniatura_prompts"]) != 3:
                raise ValueError("se necesitan 3 títulos y 3 miniatura_prompts")
            d["descripcion"], d["etiquetas"], d["texto_miniatura"]

        resumen = " ".join(e.narracion for e in guion.escenas)[:6000]
        ctx.reservar(EST_METADATOS)
        try:
          meta, coste = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("metadatos", {}, (
            f"Título de trabajo: {guion.titulo}\nAudiencia: {plan.audiencia}\nÁngulo: {plan.angulo}\n"
            f"Estilo visual: {guion.biblia_visual}\nGuion (extracto): {resumen}\n"
            "Genera 3 títulos (≤70 caracteres), descripción (2-3 párrafos, sin marcas de tiempo), 10-15 etiquetas, "
            "texto_miniatura (≤4 palabras) y 3 miniatura_prompts (inglés, 16:9, alto contraste, sin texto). JSON: "
            '{"titulos":[str],"descripcion":str,"etiquetas":[str],"texto_miniatura":str,"miniatura_prompts":[str]}')),
            validar=validar)
        finally:
            ctx.liberar(EST_METADATOS)
        ctx.cobrar(self.nombre, "metadatos", coste)
        coste_total = coste
        miniaturas = []
        for i, p in enumerate(meta["miniatura_prompts"], 1):
            ruta = base / f"miniatura_{i}.png"
            ctx.reservar(PRECIOS["imagen"])
            try:
                c = await con_reintentos(lambda: ctx.proveedores.imagen.generar(
                    f"{p}. Visual style: {guion.biblia_visual}", ruta))
            finally:
                ctx.liberar(PRECIOS["imagen"])
            ctx.cobrar(self.nombre, f"miniatura {i}", c)
            coste_total += c
            _rotular(ruta, meta["texto_miniatura"])
            miniaturas.append(ruta.name)
        descripcion = f"{meta['descripcion']}\n\nCapítulos:\n{marcas_capitulos(montaje['capitulos'])}"
        ctx.almacen.guardar_json(ctx.pid, "publicacion.json", {
            "titulos": meta["titulos"], "descripcion": descripcion, "etiquetas": meta["etiquetas"],
            "miniaturas": miniaturas, "titulo_elegido": None, "miniatura_elegida": None,
            "privacidad": "private", "publicar_en": None, "video_id": previo.get("video_id")})
        ctx.emitir(self.nombre, "metadatos y miniaturas listos")
        return Resultado(ok=True, coste=coste_total)

    async def subir(self, ctx: Contexto) -> Resultado:
        d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
        if not d or not d.get("titulo_elegido") or not d.get("miniatura_elegida"):
            return Resultado(ok=False, errores=["elige título y miniatura antes de publicar"])
        if d.get("video_id"):
            ctx.emitir(self.nombre, f"ya estaba publicado: {d['video_id']}")
            return Resultado(ok=True)
        if d.get("subida_iniciada"):
            return Resultado(ok=False, errores=["Una subida anterior se interrumpió: comprueba YouTube Studio. "
                                                "Si no se publicó, pulsa 'Reintentar subida'."])
        base = ctx.almacen.ruta(ctx.pid)
        errores = []
        if d["titulo_elegido"] not in d["titulos"]:
            errores.append("el título elegido no está en la lista de títulos")
        if d["miniatura_elegida"] not in d["miniaturas"]:
            errores.append("la miniatura elegida no está en la lista de miniaturas")
        if not (base / "final.mp4").exists():
            errores.append("falta final.mp4: monta el vídeo antes de publicar")
        if not (base / d["miniatura_elegida"]).exists():
            errores.append(f"no existe el archivo de miniatura {d['miniatura_elegida']}")
        if errores:
            return Resultado(ok=False, errores=errores)
        meta = {"titulo": d["titulo_elegido"], "descripcion": d["descripcion"], "etiquetas": d["etiquetas"],
                "privacidad": d["privacidad"], "publicar_en": d["publicar_en"]}
        d["subida_iniciada"] = datetime.now().isoformat(timespec="seconds")
        ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
        video_id = await con_reintentos(lambda: ctx.proveedores.subidor.subir(
            base / "final.mp4", meta, base / d["miniatura_elegida"], base / "subtitulos.srt"))
        d["video_id"] = video_id
        d.pop("subida_iniciada", None)
        ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
        ctx.emitir(self.nombre, f"subido a YouTube: {video_id}")
        return Resultado(ok=True)
