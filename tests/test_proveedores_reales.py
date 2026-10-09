import httpx
import pytest
from herramientas.reintentos import ErrorTransitorio, ErrorPermanente
from proveedores.tts import ElevenLabsTTS, OpenAITTS
from proveedores import fal as falmod
from proveedores.fabrica import construir
from proveedores.simulados import LLMSimulado
from core.config import Ajustes

def _cliente(status, body=b"ID3audio"):
    def handler(req):
        handler.req = req
        return httpx.Response(status, content=body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), handler

async def test_elevenlabs_escribe_mp3_y_cobra_por_caracter(tmp_path):
    cli, h = _cliente(200)
    tts = ElevenLabsTTS("k", "voz1", 0.30, cliente=cli)
    coste = await tts.sintetizar("a" * 1000, tmp_path / "a.mp3")
    assert (tmp_path / "a.mp3").read_bytes() == b"ID3audio"
    assert coste == pytest.approx(0.30)
    assert h.req.headers["xi-api-key"] == "k" and "voz1" in str(h.req.url)

@pytest.mark.parametrize("status,exc", [(429, ErrorTransitorio), (503, ErrorTransitorio), (400, ErrorPermanente)])
async def test_tts_mapea_errores(tmp_path, status, exc):
    cli, _ = _cliente(status, b"err")
    with pytest.raises(exc):
        await OpenAITTS("k", "onyx", 0.015, cliente=cli).sintetizar("hola", tmp_path / "a.mp3")

async def test_fal_video_sube_imagen_y_descarga(tmp_path, monkeypatch):
    llamadas = {}
    async def upload(path): llamadas["upload"] = path; return "https://fal/img.png"
    async def subscribe(endpoint, arguments): llamadas["args"] = arguments; return {"video": {"url": "https://fal/v.mp4"}}
    async def descargar(url, destino): destino.write_bytes(b"mp4")
    monkeypatch.setattr(falmod.fal_client, "upload_file_async", upload)
    monkeypatch.setattr(falmod.fal_client, "subscribe_async", subscribe)
    monkeypatch.setattr(falmod, "descargar", descargar)
    img = tmp_path / "i.png"; img.write_bytes(b"png")
    coste = await falmod.FalVideo("fal-ai/x", 0.3).animar(img, "push in", tmp_path / "c.mp4", 10)
    assert coste == 0.3 and llamadas["args"]["image_url"] == "https://fal/img.png"
    assert llamadas["args"]["duration"] == "10" and (tmp_path / "c.mp4").read_bytes() == b"mp4"

def test_fabrica_simulado_y_real_sin_claves():
    assert isinstance(construir(Ajustes(modo="simulado")).llm, LLMSimulado)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        construir(Ajustes(modo="real"))


# --- ronda de correcciones ---
from proveedores import youtube as ytmod
from proveedores.anthropic_llm import tipo_imagen


def test_youtube_fallo_miniatura_no_pierde_vid(tmp_path, monkeypatch):
    class Req:
        def next_chunk(self): return None, {"id": "VID1"}
    class Videos:
        def insert(self, **k): return Req()
    class Servicio:
        def videos(self): return Videos()
        def thumbnails(self): raise RuntimeError("boom")
        def captions(self): raise RuntimeError("boom")
    s = ytmod.SubidorYouTube(tmp_path / "c.json", tmp_path / "t.json")
    monkeypatch.setattr(s, "_servicio", lambda: Servicio())
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    srt = tmp_path / "a.srt"; srt.write_text("1")
    meta = {"titulo": "t", "descripcion": "d", "etiquetas": []}
    assert s._subir(v, meta, tmp_path / "no_existe.png", srt) == "VID1"


async def test_fal_descargar_mapea_status(tmp_path, monkeypatch):
    for status, exc in ((503, ErrorTransitorio), (404, ErrorPermanente)):
        def handler(req, status=status): return httpx.Response(status, content=b"x")
        real = httpx.AsyncClient
        monkeypatch.setattr(falmod.httpx, "AsyncClient",
                            lambda **k: real(transport=httpx.MockTransport(handler)))
        with pytest.raises(exc):
            await falmod.descargar("https://fal/x", tmp_path / "o")


async def test_fal_error_1500_con_400_es_permanente(monkeypatch):
    class E(Exception):
        status_code = 400
    async def subscribe(endpoint, arguments): raise E("campo 1500 inválido")
    monkeypatch.setattr(falmod.fal_client, "subscribe_async", subscribe)
    with pytest.raises(ErrorPermanente):
        await falmod._llamar("x", {})


def test_tipo_imagen_sniff():
    assert tipo_imagen(b"\xff\xd8\xff\xe0abc") == "image/jpeg"
    assert tipo_imagen(b"RIFF\x00\x00\x00\x00WEBPxx") == "image/webp"
    assert tipo_imagen(b"\x89PNG\r\n") == "image/png"


def test_fabrica_tts_invalido():
    with pytest.raises(ValueError, match="DV_TTS"):
        construir(Ajustes(modo="real", tts="otro"))
