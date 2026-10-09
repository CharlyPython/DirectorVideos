import base64
from pathlib import Path

import anthropic

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio
from proveedores.base import RespuestaLLM


class AnthropicLLM:
    def __init__(self, clave: str, modelo: str, precio_in: float, precio_out: float):
        """precio_in/out: USD por millón de tokens."""
        self.cliente = anthropic.AsyncAnthropic(api_key=clave)
        self.modelo, self.precio_in, self.precio_out = modelo, precio_in, precio_out

    async def _crear(self, sistema: str, contenido, max_tokens: int) -> RespuestaLLM:
        # Sin `temperature` ni `thinking`: los modelos 5.5 los rechazan/no los necesitan.
        try:
            r = await self.cliente.messages.create(model=self.modelo, max_tokens=max_tokens, system=sistema,
                                                   messages=[{"role": "user", "content": contenido}])
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            raise ErrorTransitorio(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                raise ErrorTransitorio(str(e)) from e
            raise ErrorPermanente(str(e)) from e
        texto = "".join(b.text for b in r.content if b.type == "text")
        coste = (r.usage.input_tokens * self.precio_in + r.usage.output_tokens * self.precio_out) / 1e6
        return RespuestaLLM(texto, coste)

    async def completar(self, sistema: str, prompt: str, max_tokens: int = 4000) -> RespuestaLLM:
        return await self._crear(sistema, prompt, max_tokens)

    async def evaluar_imagen(self, imagen: Path, pregunta: str) -> RespuestaLLM:
        datos = base64.standard_b64encode(imagen.read_bytes()).decode()
        contenido = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": datos}},
                     {"type": "text", "text": pregunta}]
        return await self._crear("Eres un supervisor de calidad visual. Respondes SOLO con JSON.", contenido, 300)
