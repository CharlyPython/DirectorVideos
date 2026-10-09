"""Precios orientativos en USD. VERIFICAR con las webs de cada proveedor antes de producción."""
from core.modelos import ESCENAS_POR_MINUTO, Plan

PRECIOS = {
    "guion_por_minuto": 0.05,       # Claude, esquema + narración + desglose
    "imagen": 0.025,                # Flux dev 1920x1080
    "clip": {"barato": 0.30, "premium": 1.00},   # clip 10 s
    "tts_por_minuto": 0.30,
    "publicacion": 0.20,            # metadatos + 3 miniaturas
}


def precio_unitario(clave: str, plan: Plan, precios: dict = PRECIOS) -> float:
    if clave == "imagen":
        return precios["imagen"]
    if clave == "clip":
        return precios["clip"][plan.modelo_video]
    if clave == "audio":
        return round(precios["tts_por_minuto"] / ESCENAS_POR_MINUTO, 4)
    raise KeyError(clave)


def estimar(plan: Plan, precios: dict = PRECIOS) -> dict[str, float]:
    n = plan.num_escenas
    e = {
        "guion": plan.duracion_min * precios["guion_por_minuto"],
        "imagenes": n * precios["imagen"],
        "clips": n * precios["clip"][plan.modelo_video],
        "audio": plan.duracion_min * precios["tts_por_minuto"],
        "publicacion": precios["publicacion"],
    }
    e = {k: round(v, 2) for k, v in e.items()}
    e["total"] = round(sum(e.values()), 2)
    return e
