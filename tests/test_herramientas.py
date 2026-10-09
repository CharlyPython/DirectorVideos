import pytest
from herramientas.ffmpeg import ejecutar, duracion
from herramientas.reintentos import con_reintentos, ErrorTransitorio, ErrorPermanente

async def test_duracion_de_audio_generado(tmp_path):
    destino = tmp_path / "a b ñ.mp3"
    await ejecutar(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3", str(destino)])
    assert abs(await duracion(destino) - 3.0) < 0.15

async def test_ejecutar_error_lanza(tmp_path):
    with pytest.raises(RuntimeError):
        await ejecutar(["-i", str(tmp_path / "noexiste.mp4"), str(tmp_path / "x.mp4")])

async def test_reintenta_transitorio_y_no_permanente():
    llamadas = []
    async def falla_dos():
        llamadas.append(1)
        if len(llamadas) < 3:
            raise ErrorTransitorio("429")
        return "ok"
    assert await con_reintentos(falla_dos, base=0.01) == "ok"
    async def permanente():
        llamadas.append(1)
        raise ErrorPermanente("400")
    n = len(llamadas)
    with pytest.raises(ErrorPermanente):
        await con_reintentos(permanente, base=0.01)
    assert len(llamadas) == n + 1
