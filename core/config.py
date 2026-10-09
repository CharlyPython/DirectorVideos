import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


RAIZ_REPO = Path(__file__).resolve().parent.parent


def _anclar(ruta: Path, base: Path = RAIZ_REPO) -> Path:
    return ruta if ruta.is_absolute() else (base / ruta)


@dataclass
class Ajustes:
    modo: str = "simulado"
    raiz: Path = Path("proyectos")
    concurrencia: int = 6
    anthropic_key: str = ""
    modelo_guion: str = "claude-sonnet-5-5"
    modelo_supervisor: str = "claude-opus-5-5"
    fal_key: str = ""
    fal_imagen: str = "fal-ai/flux/dev"
    fal_video_barato: str = "fal-ai/kling-video/v2.1/standard/image-to-video"
    fal_video_premium: str = "fal-ai/kling-video/v2.1/pro/image-to-video"
    tts: str = "elevenlabs"
    elevenlabs_key: str = ""
    elevenlabs_voz: str = ""
    openai_key: str = ""
    openai_voz: str = "onyx"
    youtube_client_secret: Path = Path("client_secret.json")

    @classmethod
    def desde_entorno(cls) -> "Ajustes":
        load_dotenv(RAIZ_REPO / ".env")
        load_dotenv()
        g = os.environ.get
        return cls(
            modo=g("DV_MODO", "simulado"),
            raiz=_anclar(Path(g("DV_RAIZ", "proyectos"))),
            concurrencia=max(1, min(10, int(g("DV_CONCURRENCIA", "6")))),
            anthropic_key=g("ANTHROPIC_API_KEY", ""),
            modelo_guion=g("DV_MODELO_GUION", cls.modelo_guion),
            modelo_supervisor=g("DV_MODELO_SUPERVISOR", cls.modelo_supervisor),
            fal_key=g("FAL_KEY", ""),
            fal_imagen=g("DV_FAL_IMAGEN", cls.fal_imagen),
            fal_video_barato=g("DV_FAL_VIDEO_BARATO", cls.fal_video_barato),
            fal_video_premium=g("DV_FAL_VIDEO_PREMIUM", cls.fal_video_premium),
            tts=g("DV_TTS", "elevenlabs"),
            elevenlabs_key=g("ELEVENLABS_API_KEY", ""),
            elevenlabs_voz=g("DV_ELEVENLABS_VOZ", ""),
            openai_key=g("OPENAI_API_KEY", ""),
            openai_voz=g("DV_OPENAI_VOZ", "onyx"),
            youtube_client_secret=_anclar(Path(g("DV_YOUTUBE_CLIENT_SECRET", "client_secret.json"))),
        )
