import asyncio
from pathlib import Path


async def _correr(binario: str, args: list[str], cwd: Path | None) -> str:
    proc = await asyncio.create_subprocess_exec(
        binario, *args, cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        cola = "\n".join(err.decode("utf-8", "replace").strip().splitlines()[-8:])
        raise RuntimeError(f"{binario} falló ({proc.returncode}): {cola}")
    return out.decode("utf-8", "replace")


async def ejecutar(args: list[str], cwd: Path | None = None) -> None:
    await _correr("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", *args], cwd)


async def duracion(ruta: Path) -> float:
    salida = await _correr("ffprobe", ["-v", "error", "-show_entries", "format=duration",
                                       "-of", "default=nw=1:nk=1", str(ruta)], None)
    return float(salida.strip())
