import json
import pytest
from PIL import Image
from herramientas.ffmpeg import duracion
from proveedores.base import completar_json, armar_prompt, RespuestaLLM, ErrorJSON
from proveedores.simulados import proveedores_simulados

async def test_simulados_generan_archivos(tmp_path):
    p = proveedores_simulados()
    img = tmp_path / "i.png"
    assert await p.imagen.generar("algo", img) == 0
    assert Image.open(img).size == (1920, 1080)
    clip = tmp_path / "c.mp4"
    await p.video.animar(img, "zoom", clip, 10)
    assert abs(await duracion(clip) - 10) < 0.2
    aud = tmp_path / "a.mp3"
    await p.tts.sintetizar(" ".join(["palabra"] * 30), aud)
    assert abs(await duracion(aud) - 12) < 0.3

class LLMGuionado:
    def __init__(self, respuestas): self.respuestas = list(respuestas); self.prompts = []
    async def completar(self, sistema, prompt, max_tokens=4000):
        self.prompts.append(prompt); return RespuestaLLM(self.respuestas.pop(0), 0.01)

async def test_completar_json_reintenta():
    llm = LLMGuionado(["no es json", "```json\n{\"a\": 1}\n```"])
    datos, coste = await completar_json(llm, "s", "p")
    assert datos == {"a": 1} and coste == pytest.approx(0.02)
    assert "no es JSON válido" in llm.prompts[1]

async def test_completar_json_validador_y_agota():
    llm = LLMGuionado(['{"n": 1}'] * 3)
    def validar(d):
        if d["n"] != 2: raise ValueError("n debe ser 2")
    with pytest.raises(ErrorJSON):
        await completar_json(llm, "s", "p", validar=validar)

async def test_llm_simulado_responde_por_tarea():
    p = proveedores_simulados()
    r = await p.llm.completar("s", armar_prompt("esquema", {"duracion_min": 2}, "..."))
    d = json.loads(r.texto)
    assert sum(c["minutos"] for c in d["capitulos"]) == 2
