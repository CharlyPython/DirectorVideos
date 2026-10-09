# tests/test_montador.py
from pathlib import Path
from agentes.montador import Montador, velocidad, generar_srt, formato_srt, linea_concat
from agentes.ilustrador import Ilustrador
from agentes.animador import Animador
from agentes.narrador import Narrador
from core.modelos import Escena
from herramientas.ffmpeg import duracion
from tests.ayudas import proyecto_con_guion

def test_velocidad_en_rango_y_fuera():
    v, aviso = velocidad(10, 12)
    assert abs(v - 10 / 12) < 1e-6 and aviso is None
    v, aviso = velocidad(10, 30)
    assert v == 0.6 and "fuera de rango" in aviso

def test_formato_y_srt():
    assert formato_srt(3661.5) == "01:01:01,500"
    es = [Escena(id="a", capitulo=1, narracion="hola mundo", imagen_prompt="", movimiento_prompt="", duracion_audio=2.0),
          Escena(id="b", capitulo=1, narracion="adiós", imagen_prompt="", movimiento_prompt="", duracion_audio=3.0)]
    srt = generar_srt(es)
    assert "00:00:00,000 --> 00:00:02,000" in srt and "00:00:02,000 --> 00:00:05,000" in srt

def test_lista_concat_escapa_rutas():
    assert linea_concat(Path("C:/Mis vídeos/it's/seg.mp4")) == "file 'C:/Mis vídeos/it'\\''s/seg.mp4'"

async def _producido(raiz):
    ctx = await proyecto_con_guion(raiz)
    for ag in (Ilustrador(), Animador(), Narrador()):
        await ag.ejecutar(ctx)
    return ctx

async def test_monta_video_final(raiz):
    ctx = await _producido(raiz)
    r = await Montador().ejecutar(ctx)
    final = ctx.almacen.ruta(ctx.pid) / "final.mp4"
    assert r.ok and final.exists()
    assert abs(await duracion(final) - 60) < 1.5
    m = ctx.almacen.cargar_json(ctx.pid, "montaje.json")
    assert m["capitulos"][0]["inicio"] == 0
    assert (ctx.almacen.ruta(ctx.pid) / "subtitulos.srt").exists()

async def test_audio_largo_genera_aviso_y_no_falla(raiz):
    ctx = await _producido(raiz)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[0].narracion = " ".join(["larga"] * 80)          # ~32 s
    ctx.almacen.guardar_guion(ctx.pid, g)
    await Narrador().ejecutar(ctx, solo=[g.escenas[0].id])
    r = await Montador().ejecutar(ctx)
    m = ctx.almacen.cargar_json(ctx.pid, "montaje.json")
    assert r.ok and any(g.escenas[0].id in a for a in m["avisos"])

async def test_no_monta_si_faltan_piezas(raiz):
    ctx = await proyecto_con_guion(raiz)
    r = await Montador().ejecutar(ctx)
    assert not r.ok and r.errores


async def test_musica_y_subtitulos_incrustados(raiz):
    from herramientas.ffmpeg import ejecutar
    ctx = await _producido(raiz)
    musica = raiz / "música.mp3"
    await ejecutar(["-f", "lavfi", "-i", "sine=frequency=440", "-t", "5", str(musica)])
    plan = ctx.plan; plan.musica = str(musica); plan.subtitulos_incrustados = True
    ctx.almacen.guardar_plan(ctx.pid, plan)
    r = await Montador().ejecutar(ctx)
    assert r.ok and abs(await duracion(ctx.almacen.ruta(ctx.pid) / "final.mp4") - 60) < 1.5
