from core.costes import estimar, precio_unitario, PRECIOS
from core.modelos import Plan

def test_estimar_20_min_barato():
    e = estimar(Plan(idea="x", duracion_min=20, modelo_video="barato"))
    assert e["clips"] == round(100 * PRECIOS["clip"]["barato"], 2)
    assert e["imagenes"] == round(100 * PRECIOS["imagen"], 2)
    assert e["total"] == round(sum(v for k, v in e.items() if k != "total"), 2)

def test_premium_mas_caro_y_unitario():
    p = Plan(idea="x", duracion_min=5, modelo_video="premium")
    assert estimar(p)["clips"] > estimar(Plan(idea="x", duracion_min=5))["clips"]
    assert precio_unitario("clip", p) == PRECIOS["clip"]["premium"]
    assert precio_unitario("audio", p) == round(PRECIOS["tts_por_minuto"] / 5, 4)
