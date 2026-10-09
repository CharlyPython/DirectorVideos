import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


@dataclass
class RespuestaLLM:
    texto: str
    coste: float


class LLM(Protocol):
    async def completar(self, sistema: str, prompt: str, max_tokens: int = 4000) -> RespuestaLLM: ...
    async def evaluar_imagen(self, imagen: Path, pregunta: str) -> RespuestaLLM: ...


class GeneradorImagen(Protocol):
    async def generar(self, prompt: str, destino: Path) -> float: ...


class GeneradorVideo(Protocol):
    async def animar(self, imagen: Path, prompt: str, destino: Path, segundos: float = 10.0) -> float: ...


class TTS(Protocol):
    async def sintetizar(self, texto: str, destino: Path) -> float: ...


class Subidor(Protocol):
    async def subir(self, video: Path, meta: dict, miniatura: Path, srt: Path | None) -> str: ...


@dataclass
class Proveedores:
    llm: LLM            # redacción (Guionista, Publicador)
    supervisor: LLM     # Arquitecto
    imagen: GeneradorImagen
    video: GeneradorVideo
    tts: TTS
    subidor: Subidor


class ErrorJSON(Exception):
    pass


def armar_prompt(tarea: str, params: dict, cuerpo: str) -> str:
    return f"TAREA: {tarea}\nPARAMS: {json.dumps(params, ensure_ascii=False)}\n\n{cuerpo}"


def extraer_json(texto: str) -> Any:
    bloque = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    candidato = bloque.group(1) if bloque else texto
    inicio = min([i for i in (candidato.find("{"), candidato.find("[")) if i >= 0], default=-1)
    if inicio < 0:
        raise ValueError("no hay JSON")
    return json.JSONDecoder().raw_decode(candidato[inicio:])[0]


async def completar_json(llm: LLM, sistema: str, prompt: str, max_tokens: int = 4000,
                         validar: Callable[[Any], None] | None = None, intentos: int = 3) -> tuple[Any, float]:
    coste, actual, ultimo = 0.0, prompt, ""
    for _ in range(intentos):
        r = await llm.completar(sistema, actual, max_tokens)
        coste += r.coste
        try:
            datos = extraer_json(r.texto)
            if validar:
                validar(datos)
            return datos, coste
        except (ValueError, KeyError, TypeError) as e:
            ultimo = str(e)
            actual = (f"{prompt}\n\nTu respuesta anterior no es JSON válido o no cumple: {ultimo}. "
                      "Responde SOLO con el JSON corregido.")
    raise ErrorJSON(f"El LLM no devolvió JSON válido tras {intentos} intentos: {ultimo}")
