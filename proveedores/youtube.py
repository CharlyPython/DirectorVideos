import asyncio
import logging
from pathlib import Path

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio

ALCANCES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
log = logging.getLogger(__name__)


def conectar_youtube(client_secret: Path, token: Path) -> None:
    """Abre el navegador para que el usuario autorice su canal. Guarda el token en local."""
    flujo = InstalledAppFlow.from_client_secrets_file(str(client_secret), ALCANCES)
    cred = flujo.run_local_server(port=0)
    token.write_text(cred.to_json(), encoding="utf-8")


def youtube_conectado(token: Path) -> bool:
    return token.exists()


class SubidorYouTube:
    """Errores durante la subida -> ErrorPermanente (sin reintento automático): reintentar tras un éxito
    del lado servidor duplicaría el vídeo. Fallos de miniatura/subtítulos tras la subida no lanzan."""

    def __init__(self, client_secret: Path, token: Path):
        self.client_secret, self.token = client_secret, token

    def _servicio(self):
        if not self.token.exists():
            raise ErrorPermanente("YouTube no conectado: ve a Ajustes → Conectar YouTube")
        try:
            cred = Credentials.from_authorized_user_file(str(self.token), ALCANCES)
            if cred.expired and cred.refresh_token:
                cred.refresh(Request())
                self.token.write_text(cred.to_json(), encoding="utf-8")
        except TransportError as e:  # nada subido todavía: reintento seguro
            raise ErrorTransitorio(str(e)) from e
        except (RefreshError, ValueError) as e:
            raise ErrorPermanente("YouTube desconectado: reconecta en Ajustes") from e
        return build("youtube", "v3", credentials=cred)

    def _subir(self, video: Path, meta: dict, miniatura: Path, srt: Path | None) -> str:
        yt = self._servicio()
        estado = {"privacyStatus": meta.get("privacidad", "private"), "selfDeclaredMadeForKids": False}
        if meta.get("publicar_en"):
            estado.update(privacyStatus="private", publishAt=meta["publicar_en"])
        cuerpo = {"snippet": {"title": meta["titulo"], "description": meta["descripcion"],
                              "tags": meta["etiquetas"], "defaultLanguage": "es", "defaultAudioLanguage": "es"},
                  "status": estado}
        try:
            req = yt.videos().insert(part="snippet,status", body=cuerpo,
                                     media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
            resp = None
            while resp is None:
                _, resp = req.next_chunk()
            vid = resp["id"]
        except HttpError as e:
            raise ErrorPermanente(str(e)) from e
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(miniatura))).execute()
        except Exception as e:  # noqa: BLE001
            log.warning("miniatura no subida para %s: %s", vid, type(e).__name__)
        try:
            if srt and srt.exists():
                yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "es",
                                                                       "name": "Español"}},
                                     media_body=MediaFileUpload(str(srt))).execute()
        except Exception as e:  # noqa: BLE001
            log.warning("subtítulos no subidos para %s: %s", vid, type(e).__name__)
        return vid

    async def subir(self, video: Path, meta: dict, miniatura: Path, srt: Path | None) -> str:
        return await asyncio.to_thread(self._subir, video, meta, miniatura, srt)
