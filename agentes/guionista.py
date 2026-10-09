# agentes/guionista.py
from core.modelos import (CLAVES, PALABRAS_POR_SEGUNDO, SEGUNDOS_POR_ESCENA,
                          Capitulo, Escena, Estado, Guion)
from agentes.base import Resultado
from director.contexto import Contexto
from proveedores.base import armar_prompt, completar_json

SISTEMA = ("Eres guionista de documentales faceless para YouTube. Escribes en español, con ritmo, "
           "datos concretos y ganchos de retención. Respondes SOLO con JSON válido.")


def repartir(minutos: list[float], total: int) -> list[int]:
    """Reparte `total` escenas proporcionalmente a los minutos (mayor resto)."""
    suma = sum(minutos)
    exactos = [m / suma * total for m in minutos]
    base = [int(x) for x in exactos]
    restos = sorted(range(len(minutos)), key=lambda i: exactos[i] - base[i], reverse=True)
    for i in restos[: total - sum(base)]:
        base[i] += 1
    if total >= len(base):
        for i in range(len(base)):
            if base[i] == 0:
                j = max(range(len(base)), key=lambda k: base[k])
                base[j] -= 1
                base[i] = 1
    return base


def _no_vacia(d):
    if not d["narracion"].strip():
        raise ValueError("narración vacía")


class Guionista:
    nombre = "guionista"

    async def ejecutar(self, ctx: Contexto) -> Resultado:
        plan = ctx.plan
        coste = 0.0

        def validar_esquema(d):
            if not (d["titulo"] and d["capitulos"]):
                raise ValueError("faltan titulo/capitulos")
            n = len(d["capitulos"])
            if n < 1 or n > 12 or n > plan.num_escenas:
                raise ValueError(f"número de capítulos inválido: {n}")
            for c in d["capitulos"]:
                if float(c["minutos"]) <= 0:
                    raise ValueError("los minutos de cada capítulo deben ser > 0")
                c["titulo"]

        esquema, c = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("esquema", {
            "duracion_min": plan.duracion_min}, (
            f"Idea: {plan.idea}\nTono: {plan.tono}\nAudiencia: {plan.audiencia}\nÁngulo: {plan.angulo}\n"
            f"Duración total: {plan.duracion_min} min. Diseña entre 1 y 12 capítulos cuya suma de minutos sea "
            f"{plan.duracion_min}. Incluye un gancho de 30 s y una biblia visual (estilo base: {plan.estilo_visual}; "
            "paleta, época, personajes recurrentes). JSON: "
            '{"titulo":str,"gancho":str,"biblia_visual":str,"capitulos":[{"numero":int,"titulo":str,"minutos":float}]}')),
            validar=validar_esquema)
        coste += c
        ctx.emitir(self.nombre, f"esquema: {len(esquema['capitulos'])} capítulos")

        capitulos = [Capitulo(numero=i + 1, titulo=x["titulo"], minutos=float(x["minutos"]))
                     for i, x in enumerate(esquema["capitulos"])]
        cuotas = repartir([x.minutos for x in capitulos], plan.num_escenas)
        escenas: list[Escena] = []
        resumen_previo = esquema["gancho"]
        for cap, n in zip(capitulos, cuotas):
            nuevas, c = await self._capitulo(ctx, esquema, cap, n, resumen_previo, len(escenas))
            coste += c
            escenas += nuevas
            resumen_previo = " ".join(e.narracion for e in nuevas)[-1500:]
            ctx.emitir(self.nombre, f"capítulo {cap.numero}/{len(capitulos)} listo", hechas=cap.numero,
                       total=len(capitulos))

        guion = Guion(titulo=esquema["titulo"], gancho=esquema["gancho"], biblia_visual=esquema["biblia_visual"],
                      capitulos=capitulos, escenas=escenas)
        ctx.almacen.guardar_guion(ctx.pid, guion)
        ctx.cobrar(self.nombre, "guion", coste)
        return Resultado(ok=True, coste=coste)

    async def _capitulo(self, ctx, esquema, cap: Capitulo, n: int, previo: str, offset: int):
        palabras = int(n * SEGUNDOS_POR_ESCENA * PALABRAS_POR_SEGUNDO)
        narr, c1 = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("narracion", {
            "palabras": palabras}, (
            f"Vídeo: {esquema['titulo']}\nCapítulo {cap.numero}: {cap.titulo}\n"
            f"Final de lo narrado antes (no lo repitas): {previo}\n"
            f"Escribe la narración de este capítulo, unas {palabras} palabras. JSON: {{\"narracion\": str}}")),
            max_tokens=8000, validar=_no_vacia)

        def validar(d):
            if len(d["escenas"]) != n:
                raise ValueError(f"se pidieron exactamente {n} escenas y llegaron {len(d['escenas'])}")
            for e in d["escenas"]:
                e["narracion"], e["imagen_prompt"], e["movimiento_prompt"]

        desg, c2 = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("escenas", {"n": n}, (
            f"Biblia visual: {esquema['biblia_visual']}\nNarración:\n{narr['narracion']}\n\n"
            f"Divide la narración en EXACTAMENTE {n} escenas consecutivas de ~{int(SEGUNDOS_POR_ESCENA)} s "
            f"(~{int(SEGUNDOS_POR_ESCENA * PALABRAS_POR_SEGUNDO)} palabras). Para cada una: narracion (texto literal), "
            "imagen_prompt (inglés, descriptivo, 16:9) y movimiento_prompt (inglés, movimiento de cámara y elementos). "
            'JSON: {"escenas":[{"narracion":str,"imagen_prompt":str,"movimiento_prompt":str}]}')),
            max_tokens=8000, validar=validar)
        escenas = [Escena(id=f"c{cap.numero:02d}_s{offset + i + 1:03d}", capitulo=cap.numero, **e)
                   for i, e in enumerate(desg["escenas"])]
        return escenas, c1 + c2

    async def regenerar_escena(self, ctx: Contexto, escena_id: str, motivo: str = "") -> None:
        guion = ctx.almacen.cargar_guion(ctx.pid)
        e = guion.escena(escena_id)
        i = guion.escenas.index(e)
        vecinas = " ".join(x.narracion for x in guion.escenas[max(0, i - 1): i + 2] if x.id != e.id)
        d, c = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("escena", {}, (
            f"Biblia visual: {guion.biblia_visual}\nContexto: {vecinas}\nEscena actual: {e.narracion}\n"
            f"Motivo de reescritura: {motivo or 'mejorar'}\nReescribe la escena (~30 palabras). "
            'JSON: {"narracion":str,"imagen_prompt":str,"movimiento_prompt":str}')))
        e.narracion, e.imagen_prompt, e.movimiento_prompt = d["narracion"], d["imagen_prompt"], d["movimiento_prompt"]
        e.estado = {k: Estado.PENDIENTE for k in CLAVES}
        e.duracion_audio = None
        ctx.almacen.guardar_guion(ctx.pid, guion)
        ctx.cobrar(self.nombre, f"regen {escena_id}", c)

    async def regenerar_capitulo(self, ctx: Contexto, numero: int) -> None:
        guion = ctx.almacen.cargar_guion(ctx.pid)
        cap = next(c for c in guion.capitulos if c.numero == numero)
        viejas = [e for e in guion.escenas if e.capitulo == numero]
        inicio = guion.escenas.index(viejas[0])
        previo = " ".join(e.narracion for e in guion.escenas[:inicio])[-1500:] or guion.gancho
        esquema = {"titulo": guion.titulo, "biblia_visual": guion.biblia_visual}
        nuevas, c = await self._capitulo(ctx, esquema, cap, len(viejas), previo, inicio)
        for vieja, nueva in zip(viejas, nuevas):
            nueva.id = vieja.id
        guion.escenas[inicio: inicio + len(viejas)] = nuevas
        ctx.almacen.guardar_guion(ctx.pid, guion)
        ctx.cobrar(self.nombre, f"regen cap {numero}", c)
