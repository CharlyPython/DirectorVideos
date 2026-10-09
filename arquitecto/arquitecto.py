import random
from datetime import datetime
from pathlib import Path

from core.modelos import MAX_REGENERACIONES, Estado, Plan
from director.contexto import Contexto
from herramientas.ffmpeg import duracion
from proveedores.base import LLM, armar_prompt, completar_json, extraer_json

SISTEMA = ("Eres el Arquitecto de una productora de documentales faceless para YouTube: planificas, "
           "supervisas la calidad y cuidas el presupuesto. Respondes SOLO con JSON válido.")


class Arquitecto:
    nombre = "arquitecto"

    async def planificar(self, supervisor: LLM, idea: str, duracion_min: int, tono: str,
                         presupuesto_max: float) -> tuple[Plan, float]:
        d, coste = await completar_json(supervisor, SISTEMA, armar_prompt("plan", {}, (
            f"Idea: {idea}\nDuración: {duracion_min} min\nTono: {tono}\nPresupuesto: {presupuesto_max} $\n"
            "Define estilo_visual (inglés, para prompts de imagen), audiencia, angulo (enfoque narrativo) y "
            "modelo_video ('barato' o 'premium', según presupuesto). JSON: "
            '{"estilo_visual":str,"audiencia":str,"angulo":str,"modelo_video":str}')))
        plan = Plan(idea=idea, duracion_min=duracion_min, tono=tono, presupuesto_max=presupuesto_max,
                    estilo_visual=d.get("estilo_visual") or Plan.model_fields["estilo_visual"].default,
                    audiencia=d.get("audiencia", ""), angulo=d.get("angulo", ""),
                    modelo_video=d.get("modelo_video") if d.get("modelo_video") in ("barato", "premium") else "barato")
        return plan, coste

    def _filtrar(self, ctx: Contexto, candidatos: list[tuple[str, str]]) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        vistos, salida = set(), []
        for i, m in candidatos:
            try:
                e = g.escena(i)
            except KeyError:
                continue
            if i not in vistos and e.regeneraciones < MAX_REGENERACIONES:
                vistos.add(i)
                salida.append((i, m))
        return salida

    async def revisar_guion(self, ctx: Contexto) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        candidatos = []
        for e in g.escenas:
            n = len(e.narracion.split())
            if n < 10 or n > 45:
                candidatos.append((e.id, f"{n} palabras (objetivo ~30)"))
        texto = "\n".join(f"[{e.id}] {e.narracion}" for e in g.escenas)[:60000]
        d, coste = await completar_json(ctx.proveedores.supervisor, SISTEMA, armar_prompt("revision_guion", {}, (
            f"Revisa el guion. Señala SOLO escenas con repeticiones claras, contradicciones o errores factuales "
            f"evidentes.\n{texto}\nJSON: {{\"regenerar\":[{{\"id\":str,\"motivo\":str}}]}}")), max_tokens=2000)
        candidatos += [(x["id"], x["motivo"]) for x in d.get("regenerar", [])]
        ctx.cobrar(self.nombre, "revision guion", coste)
        return self._filtrar(ctx, candidatos)

    async def revisar_imagenes(self, ctx: Contexto, muestra: int = 8) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        hechas = [e for e in g.escenas if e.estado["imagen"] == Estado.GENERADO]
        elegidas = random.sample(hechas, min(muestra, len(hechas)))
        malas, coste = [], 0.0
        for e in elegidas:
            r = await ctx.proveedores.supervisor.evaluar_imagen(
                ctx.almacen.archivo(ctx.pid, "imagen", e.id),
                f"Biblia visual: {g.biblia_visual}\nDebe mostrar: {e.imagen_prompt}\n"
                '¿Es coherente con el estilo y sin defectos graves (manos deformes, texto basura)? '
                'JSON: {"ok":bool,"motivo":str}')
            coste += r.coste
            d = extraer_json(r.texto)
            if not d.get("ok", True):
                malas.append((e.id, d.get("motivo", "")))
        ctx.cobrar(self.nombre, "revision imagenes", coste)
        return self._filtrar(ctx, sorted(malas))

    async def revisar_clips(self, ctx: Contexto) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        malos = []
        for e in g.escenas:
            if e.estado["clip"] != Estado.GENERADO:
                continue
            try:
                if await duracion(ctx.almacen.archivo(ctx.pid, "clip", e.id)) < 9.0:
                    malos.append((e.id, "clip demasiado corto"))
            except Exception:  # noqa: BLE001
                malos.append((e.id, "clip ilegible"))
        return self._filtrar(ctx, malos)

    def marcar_regeneracion(self, ctx: Contexto, ids: list[str]) -> None:
        g = ctx.almacen.cargar_guion(ctx.pid)
        for i in ids:
            g.escena(i).regeneraciones += 1
        ctx.almacen.guardar_guion(ctx.pid, g)

    def informe(self, ctx: Contexto) -> Path:
        g, plan = ctx.almacen.cargar_guion(ctx.pid), ctx.plan
        costes = ctx.almacen.costes_por_agente(ctx.pid)
        montaje = ctx.almacen.cargar_json(ctx.pid, "montaje.json") or {}
        pub = ctx.almacen.cargar_json(ctx.pid, "publicacion.json") or {}
        regen = [e for e in g.escenas if e.regeneraciones]
        lineas = [f"# Informe — {g.titulo}", f"Generado: {datetime.now():%Y-%m-%d %H:%M}", "",
                  f"- Idea: {plan.idea}", f"- Duración: {montaje.get('duracion', 0) / 60:.1f} min · "
                  f"{len(g.escenas)} escenas", f"- Modelo de vídeo: {plan.modelo_video}",
                  f"- **Coste total: {ctx.almacen.coste_total(ctx.pid):.2f} $** (tope {plan.presupuesto_max:.2f} $)",
                  "", "## Coste por agente", *[f"- {a}: {u:.2f} $" for a, u in costes.items()],
                  "", "## Regeneraciones", *([f"- {e.id}: {e.regeneraciones}" for e in regen] or ["- ninguna"]),
                  "", "## Avisos de montaje", *([f"- {a}" for a in montaje.get("avisos", [])] or ["- ninguno"]),
                  "", f"## Publicación\n- Vídeo: {pub.get('video_id') or 'no publicado'}"]
        ruta = ctx.almacen.ruta(ctx.pid) / "informe.md"
        ruta.write_text("\n".join(lineas), encoding="utf-8")
        return ruta
