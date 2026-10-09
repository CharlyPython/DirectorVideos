import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from core.modelos import PALABRAS_POR_SEGUNDO
from herramientas.ffmpeg import ejecutar
from proveedores.base import Proveedores, RespuestaLLM


def _params(prompt: str) -> tuple[str, dict]:
    tarea, params = "", {}
    for linea in prompt.splitlines():
        if linea.startswith("TAREA:"):
            tarea = linea[6:].strip()
        elif linea.startswith("PARAMS:"):
            params = json.loads(linea[7:].strip())
    return tarea, params


class LLMSimulado:
    """Devuelve respuestas sintéticas válidas según la TAREA del prompt."""

    async def completar(self, sistema: str, prompt: str, max_tokens: int = 4000) -> RespuestaLLM:
        tarea, p = _params(prompt)
        if tarea == "plan":
            d = {"estilo_visual": "cinematic digital painting", "audiencia": "curiosos de historia",
                 "angulo": "misterio", "modelo_video": "barato", "voz": ""}
        elif tarea == "esquema":
            n = p["duracion_min"]
            d = {"titulo": "Título simulado", "gancho": "Gancho simulado.",
                 "biblia_visual": "óleo cinematográfico, tonos ocres",
                 "capitulos": [{"numero": i + 1, "titulo": f"Capítulo {i + 1}", "minutos": 1} for i in range(n)]}
        elif tarea == "narracion":
            frase = "Esta es una frase de narración simulada con varias palabras. "
            d = {"narracion": frase * max(1, int(p["palabras"] / 10))}
        elif tarea == "escenas":
            d = {"escenas": [{"narracion": " ".join(["palabra"] * 30),
                              "imagen_prompt": f"escena {i}", "movimiento_prompt": "slow push-in"}
                             for i in range(p["n"])]}
        elif tarea == "revision_guion":
            d = {"regenerar": []}
        elif tarea == "escena":
            d = {"narracion": " ".join(["nueva"] * 30), "imagen_prompt": "nueva", "movimiento_prompt": "pan"}
        elif tarea == "metadatos":
            d = {"titulos": ["Título A", "Título B", "Título C"], "descripcion": "Descripción simulada.",
                 "etiquetas": ["historia", "documental"], "texto_miniatura": "¿QUÉ PASÓ?",
                 "miniatura_prompts": ["mini 1", "mini 2", "mini 3"]}
        else:
            d = {}
        return RespuestaLLM(json.dumps(d, ensure_ascii=False), 0.0)

    async def evaluar_imagen(self, imagen: Path, pregunta: str) -> RespuestaLLM:
        return RespuestaLLM('{"ok": true, "motivo": ""}', 0.0)


class ImagenSimulada:
    async def generar(self, prompt: str, destino: Path) -> float:
        h = hashlib.md5(prompt.encode()).digest()
        img = Image.new("RGB", (1920, 1080), (h[0], h[1], h[2]))
        ImageDraw.Draw(img).text((60, 60), prompt[:80], fill=(255, 255, 255))
        img.save(destino)
        return 0.0


class VideoSimulado:
    async def animar(self, imagen: Path, prompt: str, destino: Path, segundos: float = 10.0) -> float:
        await ejecutar(["-loop", "1", "-i", str(imagen), "-t", str(segundos), "-vf", "scale=1920:1080,fps=25",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(destino)])
        return 0.0


class TTSSimulado:
    async def sintetizar(self, texto: str, destino: Path) -> float:
        segundos = max(1.0, len(texto.split()) / PALABRAS_POR_SEGUNDO)
        await ejecutar(["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", f"{segundos:.2f}",
                        "-af", "volume=0.05", "-c:a", "libmp3lame", str(destino)])
        return 0.0


class SubidorSimulado:
    def __init__(self):
        self.subidas: list[dict] = []

    async def subir(self, video: Path, meta: dict, miniatura: Path, srt: Path | None) -> str:
        self.subidas.append({"video": video, "meta": meta, "miniatura": miniatura, "srt": srt})
        return "SIMULADO123"


def proveedores_simulados() -> Proveedores:
    llm = LLMSimulado()
    return Proveedores(llm=llm, supervisor=llm, imagen=ImagenSimulada(), video=VideoSimulado(),
                       tts=TTSSimulado(), subidor=SubidorSimulado())
