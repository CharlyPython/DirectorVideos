# Endpoints y esquemas de fal.ai: orientativos, verificar en la primera ejecución real.
from pathlib import Path

import fal_client
import httpx

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio


async def descargar(url: str, destino: Path) -> None:
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.get(url)
        r.raise_for_status()
        destino.write_bytes(r.content)


async def _llamar(endpoint: str, argumentos: dict) -> dict:
    try:
        return await fal_client.subscribe_async(endpoint, arguments=argumentos)
    except httpx.TransportError as e:
        raise ErrorTransitorio(str(e)) from e
    except Exception as e:  # fal_client lanza errores HTTP propios
        texto = str(e)
        if any(c in texto for c in ("429", "500", "502", "503", "504", "timeout")):
            raise ErrorTransitorio(texto) from e
        raise ErrorPermanente(texto) from e


class FalImagen:
    def __init__(self, endpoint: str, precio: float):
        self.endpoint, self.precio = endpoint, precio

    async def generar(self, prompt: str, destino: Path) -> float:
        r = await _llamar(self.endpoint, {"prompt": prompt, "image_size": {"width": 1920, "height": 1080},
                                          "num_images": 1})
        await descargar(r["images"][0]["url"], destino)
        return self.precio


class FalVideo:
    def __init__(self, endpoint: str, precio: float):
        self.endpoint, self.precio = endpoint, precio

    async def animar(self, imagen: Path, prompt: str, destino: Path, segundos: float = 10.0) -> float:
        url = await fal_client.upload_file_async(imagen)
        r = await _llamar(self.endpoint, {"prompt": prompt, "image_url": url, "duration": str(int(segundos))})
        await descargar(r["video"]["url"], destino)
        return self.precio
