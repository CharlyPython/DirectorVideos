# Endpoints y esquemas de fal.ai: orientativos, verificar en la primera ejecución real.
from pathlib import Path

import fal_client
import httpx

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio


def _clasificar(e: Exception) -> Exception:
    """Mapea por código HTTP (.status_code o .response.status_code); 'timeout' en el texto como último recurso."""
    if isinstance(e, (httpx.TransportError, TimeoutError)):
        return ErrorTransitorio(str(e))
    codigo = getattr(e, "status_code", None)
    if codigo is None:
        codigo = getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(codigo, int):
        if codigo in (408, 429) or codigo >= 500:
            return ErrorTransitorio(str(e))
        return ErrorPermanente(str(e))
    if "timeout" in str(e).lower():
        return ErrorTransitorio(str(e))
    return ErrorPermanente(str(e))


async def descargar(url: str, destino: Path) -> None:
    try:
        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.get(url)
            r.raise_for_status()
        destino.write_bytes(r.content)
    except Exception as e:  # noqa: BLE001
        raise _clasificar(e) from e


async def _subir(imagen: Path) -> str:
    try:
        return await fal_client.upload_file_async(imagen)
    except Exception as e:  # noqa: BLE001
        raise _clasificar(e) from e


async def _llamar(endpoint: str, argumentos: dict) -> dict:
    try:
        return await fal_client.subscribe_async(endpoint, arguments=argumentos)
    except Exception as e:  # noqa: BLE001
        raise _clasificar(e) from e


class FalImagen:
    def __init__(self, endpoint: str, precio: float):
        self.endpoint, self.precio = endpoint, precio

    async def generar(self, prompt: str, destino: Path) -> float:
        r = await _llamar(self.endpoint, {"prompt": prompt, "image_size": {"width": 1920, "height": 1080},
                                          "num_images": 1, "output_format": "png"})
        await descargar(r["images"][0]["url"], destino)
        return self.precio


class FalVideo:
    def __init__(self, endpoint: str, precio: float):
        self.endpoint, self.precio = endpoint, precio

    async def animar(self, imagen: Path, prompt: str, destino: Path, segundos: float = 10.0) -> float:
        url = await _subir(imagen)
        r = await _llamar(self.endpoint, {"prompt": prompt, "image_url": url, "duration": str(int(segundos))})
        await descargar(r["video"]["url"], destino)
        return self.precio
