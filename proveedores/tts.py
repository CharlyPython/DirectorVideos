# Endpoints y precios de TTS: orientativos, verificar en la primera ejecución real.
from pathlib import Path

import httpx

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio


async def _post(cliente: httpx.AsyncClient, url: str, headers: dict, cuerpo: dict) -> bytes:
    try:
        r = await cliente.post(url, headers=headers, json=cuerpo, timeout=120)
    except httpx.TransportError as e:
        raise ErrorTransitorio(str(e)) from e
    if r.status_code == 429 or r.status_code >= 500:
        raise ErrorTransitorio(f"{r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        raise ErrorPermanente(f"{r.status_code}: {r.text[:200]}")
    return r.content


class ElevenLabsTTS:
    def __init__(self, clave: str, voz: str, precio_por_1k_car: float, cliente: httpx.AsyncClient | None = None,
                 modelo: str = "eleven_multilingual_v2"):
        self.clave, self.voz, self.precio, self.modelo = clave, voz, precio_por_1k_car, modelo
        self.cliente = cliente or httpx.AsyncClient()

    async def sintetizar(self, texto: str, destino: Path) -> float:
        audio = await _post(self.cliente, f"https://api.elevenlabs.io/v1/text-to-speech/{self.voz}",
                            {"xi-api-key": self.clave, "accept": "audio/mpeg"},
                            {"text": texto, "model_id": self.modelo})
        destino.write_bytes(audio)
        return len(texto) / 1000 * self.precio


class OpenAITTS:
    def __init__(self, clave: str, voz: str, precio_por_1k_car: float, cliente: httpx.AsyncClient | None = None,
                 modelo: str = "gpt-4o-mini-tts"):
        self.clave, self.voz, self.precio, self.modelo = clave, voz, precio_por_1k_car, modelo
        self.cliente = cliente or httpx.AsyncClient()

    async def sintetizar(self, texto: str, destino: Path) -> float:
        audio = await _post(self.cliente, "https://api.openai.com/v1/audio/speech",
                            {"Authorization": f"Bearer {self.clave}"},
                            {"model": self.modelo, "voice": self.voz, "input": texto, "response_format": "mp3"})
        destino.write_bytes(audio)
        return len(texto) / 1000 * self.precio
