import os
from pathlib import Path

from core.config import Ajustes
from core.costes import PRECIOS
from proveedores.base import Proveedores
from proveedores.simulados import proveedores_simulados

# USD por millón de tokens (entrada, salida), confirmados.
PRECIOS_LLM = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}
# Orientativo: verificar en la primera ejecución real (igual que endpoints y precios de fal/ElevenLabs/OpenAI).
PRECIO_TTS_1K = {"elevenlabs": 0.30, "openai": 0.015}
TOKEN_YOUTUBE = Path(__file__).resolve().parent.parent / "token_youtube.json"


def construir(a: Ajustes) -> Proveedores:
    if a.modo == "simulado":
        return proveedores_simulados()
    if a.tts not in ("elevenlabs", "openai"):
        raise ValueError(f"DV_TTS inválido: {a.tts!r} (usa 'elevenlabs' u 'openai')")
    faltan = [n for n, v in [("ANTHROPIC_API_KEY", a.anthropic_key), ("FAL_KEY", a.fal_key)] if not v]
    if a.tts == "elevenlabs" and not (a.elevenlabs_key and a.elevenlabs_voz):
        faltan.append("ELEVENLABS_API_KEY/DV_ELEVENLABS_VOZ")
    if a.tts == "openai" and not a.openai_key:
        faltan.append("OPENAI_API_KEY")
    if faltan:
        raise ValueError("Faltan claves en .env: " + ", ".join(faltan))

    # fal_client lee FAL_KEY del entorno (las funciones a nivel de módulo no aceptan clave explícita).
    os.environ["FAL_KEY"] = a.fal_key
    from proveedores.anthropic_llm import AnthropicLLM
    from proveedores.fal import FalImagen, FalVideo
    from proveedores.tts import ElevenLabsTTS, OpenAITTS
    from proveedores.youtube import SubidorYouTube

    tts = (ElevenLabsTTS(a.elevenlabs_key, a.elevenlabs_voz, PRECIO_TTS_1K["elevenlabs"]) if a.tts == "elevenlabs"
           else OpenAITTS(a.openai_key, a.openai_voz, PRECIO_TTS_1K["openai"]))
    return Proveedores(
        llm=AnthropicLLM(a.anthropic_key, a.modelo_guion, *PRECIOS_LLM.get(a.modelo_guion, (2.0, 10.0))),
        supervisor=AnthropicLLM(a.anthropic_key, a.modelo_supervisor,
                                *PRECIOS_LLM.get(a.modelo_supervisor, (4.0, 20.0))),
        imagen=FalImagen(a.fal_imagen, PRECIOS["imagen"]),
        video=_VideoPorPlan(FalVideo(a.fal_video_barato, PRECIOS["clip"]["barato"]),
                            FalVideo(a.fal_video_premium, PRECIOS["clip"]["premium"])),
        tts=tts,
        subidor=SubidorYouTube(a.youtube_client_secret, TOKEN_YOUTUBE),
    )


class _VideoPorPlan:
    """Elige barato/premium; el Director fija `modelo` antes de cada fase CLIPS."""
    def __init__(self, barato, premium):
        self.barato, self.premium, self.modelo = barato, premium, "barato"

    async def animar(self, imagen, prompt, destino, segundos=10.0):
        return await (self.premium if self.modelo == "premium" else self.barato).animar(imagen, prompt, destino, segundos)
