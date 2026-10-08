from enum import Enum
from pydantic import BaseModel, Field

ESCENAS_POR_MINUTO = 5
SEGUNDOS_CLIP = 10.0
SEGUNDOS_POR_ESCENA = 60 / ESCENAS_POR_MINUTO   # 12.0
PALABRAS_POR_SEGUNDO = 2.5                      # ~150 palabras/min
VELOCIDAD_MIN, VELOCIDAD_MAX = 0.6, 1.3
MAX_REGENERACIONES = 2
CLAVES = ("imagen", "clip", "audio")


class Fase(str, Enum):
    GUION = "guion"
    APROBACION_GUION = "aprobacion_guion"
    IMAGENES = "imagenes"
    CLIPS = "clips"
    AUDIO = "audio"
    MONTAJE = "montaje"
    APROBACION_FINAL = "aprobacion_final"
    PUBLICACION = "publicacion"
    COMPLETADO = "completado"


class Estado(str, Enum):
    PENDIENTE = "pendiente"
    GENERADO = "generado"
    ERROR = "error"


class Plan(BaseModel):
    idea: str
    duracion_min: int = Field(ge=1, le=50)
    tono: str = "documental"
    estilo_visual: str = "cinematic digital painting, dramatic lighting"
    voz: str = ""
    modelo_video: str = "barato"            # barato | premium
    presupuesto_max: float = 50.0
    audiencia: str = ""
    angulo: str = ""
    musica: str | None = None               # ruta a mp3 opcional
    subtitulos_incrustados: bool = False

    @property
    def num_escenas(self) -> int:
        return self.duracion_min * ESCENAS_POR_MINUTO


def _estado_inicial() -> dict[str, Estado]:
    return {c: Estado.PENDIENTE for c in CLAVES}


class Escena(BaseModel):
    id: str
    capitulo: int
    narracion: str
    imagen_prompt: str
    movimiento_prompt: str
    duracion_estimada: float = SEGUNDOS_POR_ESCENA
    estado: dict[str, Estado] = Field(default_factory=_estado_inicial)
    duracion_audio: float | None = None
    regeneraciones: int = 0
    error: str | None = None


class Capitulo(BaseModel):
    numero: int
    titulo: str
    minutos: float


class Guion(BaseModel):
    titulo: str
    gancho: str
    biblia_visual: str
    capitulos: list[Capitulo]
    escenas: list[Escena]

    def escena(self, id: str) -> Escena:
        for e in self.escenas:
            if e.id == id:
                return e
        raise KeyError(id)
