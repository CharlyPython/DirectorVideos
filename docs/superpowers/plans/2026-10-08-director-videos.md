# DirectorVideos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App web local que convierte una idea en un vídeo faceless de YouTube (5–50 min) mediante un Arquitecto (IA), un Director (motor) y seis agentes, con dos aprobaciones humanas y publicación final.

**Architecture:** Paquetes Python independientes: `core` (modelos + almacén SQLite/disco), `proveedores` (interfaces + implementaciones simuladas y reales), `agentes` (uno por paso, contrato común), `arquitecto` (supervisor con LLM), `director` (máquina de estados asíncrona), `app` (FastAPI + htmx + API JSON). Todo se prueba en **modo simulado** (proveedores falsos que usan FFmpeg/Pillow, coste 0).

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, htmx 1.9.12, SQLite (stdlib), pydantic v2, Pillow, FFmpeg/ffprobe, anthropic SDK, fal-client, httpx, google-api-python-client + google-auth-oauthlib, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-10-08-director-videos-design.md`

## Global Constraints

- 5 escenas por minuto de vídeo; ≈12 s de narración por escena (`ESCENAS_POR_MINUTO = 5`).
- Cada clip se genera de 10 s (`SEGUNDOS_CLIP = 10.0`).
- Rango de ajuste de velocidad del clip en montaje: 0,6×–1,3×; fuera de rango → aviso en revisión.
- Salida `final.mp4` 1920×1080, más `subtitulos.srt`.
- Duración de proyecto 1–50 min (1 min solo para pruebas; producto 5–50).
- Máximo 2 regeneraciones por escena ordenadas por el Arquitecto (`MAX_REGENERACIONES = 2`).
- Reintentos ante errores transitorios: 3, con espera exponencial.
- Concurrencia de generación por defecto: 6 (rango 5–10).
- Nada se publica sin aprobación ⏸2; el Arquitecto nunca salta ⏸1 ni ⏸2.
- Tope de presupuesto duro por proyecto: al alcanzarse, el proyecto se pausa.
- Claves de API solo en `.env` (las introduce el usuario). Nunca se registran en logs.
- Windows 10 es la plataforma principal: rutas con espacios/acentos deben funcionar.
- Requiere `ffmpeg` y `ffprobe` en el PATH.

## Review Focus

1. **Reanudar tras caída a mitad de un paso:** escenas `generado` cuyo archivo existe no se regeneran (ni se pagan); escenas `generado` cuyo archivo falta se regeneran. → test en Task 6 (`test_reanuda_sin_repetir_y_repara_faltantes`).
2. **Presupuesto alcanzado a mitad de los clips:** el proyecto se pausa con motivo, no se lanzan más llamadas de pago y "Reanudar" tras subir el tope continúa. → test en Task 12 (`test_pausa_por_presupuesto_y_reanuda`).
3. **El LLM devuelve JSON roto o un nº de escenas distinto al pedido:** se reintenta con el error y, si persiste, se falla con un mensaje claro (sin guion corrupto). → tests en Task 3 (`test_completar_json_reintenta`) y Task 5 (`test_corrige_numero_de_escenas`).
4. **Narración muy corta o muy larga respecto al clip (velocidad fuera de 0,6–1,3×):** el montaje no falla; rellena/recorta y registra aviso. → test en Task 9 (`test_audio_largo_genera_aviso_y_no_falla`).
5. **Rutas de Windows con espacios, acentos o comillas simples en la lista de concat de FFmpeg.** → test en Task 9 (`test_lista_concat_escapa_rutas`).

---

## Estructura de archivos

```
DirectorVideos/
├─ pyproject.toml
├─ .env.example
├─ README.md
├─ run.py                         # arranca uvicorn en localhost:8000
├─ core/
│  ├─ __init__.py
│  ├─ modelos.py                  # Plan, Escena, Capitulo, Guion, Fase, Estado, constantes
│  ├─ config.py                   # Ajustes (lee .env)
│  ├─ almacen.py                  # SQLite + archivos por proyecto
│  └─ costes.py                   # tabla de precios + estimar()
├─ herramientas/
│  ├─ __init__.py
│  ├─ ffmpeg.py                   # ejecutar(), duracion()
│  └─ reintentos.py               # ErrorTransitorio, ErrorPermanente, con_reintentos()
├─ proveedores/
│  ├─ __init__.py
│  ├─ base.py                     # Protocolos + Proveedores + completar_json()
│  ├─ simulados.py                # LLMSimulado, ImagenSimulada, VideoSimulado, TTSSimulado, SubidorSimulado
│  ├─ anthropic_llm.py
│  ├─ fal.py                      # FalImagen, FalVideo
│  ├─ tts.py                      # ElevenLabsTTS, OpenAITTS
│  ├─ youtube.py                  # SubidorYouTube + OAuth
│  └─ fabrica.py                  # construir(ajustes) -> Proveedores
├─ director/
│  ├─ __init__.py
│  ├─ eventos.py                  # Bus (pub/sub para SSE)
│  ├─ contexto.py                 # Contexto, PresupuestoAgotado
│  └─ director.py                 # Director (máquina de estados)
├─ agentes/
│  ├─ __init__.py
│  ├─ base.py                     # Resultado, procesar_escenas()
│  ├─ guionista.py
│  ├─ ilustrador.py
│  ├─ animador.py
│  ├─ narrador.py
│  ├─ montador.py
│  └─ publicador.py
├─ arquitecto/
│  ├─ __init__.py
│  └─ arquitecto.py
├─ app/
│  ├─ __init__.py
│  ├─ main.py                     # crear_app()
│  ├─ api.py                      # /api/* JSON (Hermes fase 2)
│  ├─ web.py                      # páginas htmx
│  └─ templates/ base.html, panel.html, proyecto.html, _timeline.html, _escenas.html, _revision.html, ajustes.html
└─ tests/
   ├─ conftest.py
   └─ test_*.py
```

---

### Task 1: Esqueleto, configuración y modelos

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `core/__init__.py`, `core/modelos.py`, `core/config.py`, `tests/conftest.py`, `tests/test_modelos.py`

**Interfaces:**
- Produces: `core.modelos`: `ESCENAS_POR_MINUTO`, `SEGUNDOS_CLIP`, `VELOCIDAD_MIN`, `VELOCIDAD_MAX`, `MAX_REGENERACIONES`, `Fase`, `Estado`, `Plan`, `Escena`, `Capitulo`, `Guion` (con `Guion.escena(id) -> Escena`). `core.config.Ajustes.desde_entorno() -> Ajustes`.

- [ ] **Step 1: Verificar FFmpeg**

Run: `ffmpeg -version` y `ffprobe -version`
Expected: ambos imprimen versión. Si no: `winget install Gyan.FFmpeg` (lo ejecuta el usuario) y reabrir terminal.

- [ ] **Step 2: Crear `pyproject.toml`, `.gitignore`, `.env.example`**

```toml
[project]
name = "director-videos"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110", "uvicorn[standard]>=0.29", "jinja2>=3.1", "python-multipart>=0.0.9",
  "pydantic>=2.6", "python-dotenv>=1.0", "Pillow>=10.0", "httpx>=0.27",
  "anthropic>=0.40", "fal-client>=0.4",
  "google-api-python-client>=2.120", "google-auth-oauthlib>=1.2",
]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools]
packages = ["core", "herramientas", "proveedores", "director", "agentes", "arquitecto", "app"]
```

`.gitignore`:
```
.venv/
__pycache__/
.env
proyectos/
token_youtube.json
client_secret*.json
```

`.env.example`:
```
DV_MODO=simulado            # simulado | real
DV_RAIZ=proyectos
DV_CONCURRENCIA=6
ANTHROPIC_API_KEY=
DV_MODELO_GUION=claude-sonnet-5-5
DV_MODELO_SUPERVISOR=claude-opus-5-5
FAL_KEY=
DV_FAL_IMAGEN=fal-ai/flux/dev
DV_FAL_VIDEO_BARATO=fal-ai/kling-video/v2.1/standard/image-to-video
DV_FAL_VIDEO_PREMIUM=fal-ai/kling-video/v2.1/pro/image-to-video
DV_TTS=elevenlabs           # elevenlabs | openai
ELEVENLABS_API_KEY=
DV_ELEVENLABS_VOZ=
OPENAI_API_KEY=
DV_OPENAI_VOZ=onyx
DV_YOUTUBE_CLIENT_SECRET=client_secret.json
```

Then: `python -m venv .venv` · `.venv\Scripts\pip install -e .[dev]`

- [ ] **Step 3: Escribir test de modelos (falla)**

`tests/test_modelos.py`:
```python
import pytest
from pydantic import ValidationError
from core.modelos import Plan, Escena, Guion, Capitulo, Estado, ESCENAS_POR_MINUTO

def _escena(i):
    return Escena(id=f"c01_s{i:03d}", capitulo=1, narracion="x", imagen_prompt="p", movimiento_prompt="m")

def test_plan_calcula_escenas():
    assert Plan(idea="Roma", duracion_min=20).num_escenas == 20 * ESCENAS_POR_MINUTO

def test_plan_rechaza_duracion_fuera_de_rango():
    with pytest.raises(ValidationError):
        Plan(idea="x", duracion_min=51)

def test_escena_estado_inicial_pendiente():
    e = _escena(1)
    assert e.estado == {"imagen": Estado.PENDIENTE, "clip": Estado.PENDIENTE, "audio": Estado.PENDIENTE}

def test_guion_busca_escena_y_roundtrip_json():
    g = Guion(titulo="T", gancho="G", biblia_visual="B",
              capitulos=[Capitulo(numero=1, titulo="Uno", minutos=1)],
              escenas=[_escena(1), _escena(2)])
    assert g.escena("c01_s002").id == "c01_s002"
    assert Guion.model_validate_json(g.model_dump_json()) == g
    with pytest.raises(KeyError):
        g.escena("nope")
```

`tests/conftest.py`:
```python
import pytest
from pathlib import Path

@pytest.fixture
def raiz(tmp_path) -> Path:
    return tmp_path / "proyectos con espacio y ñ"
```

- [ ] **Step 4: Run** `pytest tests/test_modelos.py -v` → FAIL (`ModuleNotFoundError: core`)

- [ ] **Step 5: Implementar `core/modelos.py` y `core/config.py`** (`core/__init__.py` vacío)

```python
# core/modelos.py
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
```

```python
# core/config.py
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


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
        load_dotenv()
        g = os.environ.get
        return cls(
            modo=g("DV_MODO", "simulado"),
            raiz=Path(g("DV_RAIZ", "proyectos")),
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
            youtube_client_secret=Path(g("DV_YOUTUBE_CLIENT_SECRET", "client_secret.json")),
        )
```

- [ ] **Step 6: Run** `pytest tests/test_modelos.py -v` → PASS

- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: esqueleto, configuración y modelos"`

---

### Task 2: Almacén (SQLite + disco)

**Files:**
- Create: `core/almacen.py`, `tests/test_almacen.py`

**Interfaces:**
- Consumes: `Plan`, `Guion`, `Fase` (Task 1).
- Produces: `Almacen(raiz: Path)` con: `crear_proyecto(plan) -> str`, `ruta(pid) -> Path`, `archivo(pid, clave, escena_id) -> Path` (clave ∈ imagen|clip|audio → `imagenes/<id>.png`, `clips/<id>.mp4`, `audio/<id>.mp3`), `guardar_plan/cargar_plan`, `guardar_guion/cargar_guion`, `tiene_guion(pid) -> bool`, `guardar_json(pid, nombre, dict)`, `cargar_json(pid, nombre) -> dict | None`, `fase(pid) -> Fase`, `set_fase(pid, fase)`, `pausar(pid, motivo)`, `quitar_pausa(pid)`, `pausa(pid) -> str | None`, `registrar_coste(pid, agente, concepto, usd)`, `coste_total(pid) -> float`, `costes_por_agente(pid) -> dict[str, float]`, `coste_mes(anio, mes) -> float`, `listar() -> list[dict]` (claves: id, idea, titulo, fase, pausa, coste, creado), `log(pid, agente, mensaje)`, `logs(pid, limite=200) -> list[dict]`.

- [ ] **Step 1: Test (falla)**

```python
# tests/test_almacen.py
from datetime import datetime
from core.almacen import Almacen
from core.modelos import Plan, Guion, Capitulo, Escena, Fase

def _guion():
    return Guion(titulo="T", gancho="G", biblia_visual="B",
                 capitulos=[Capitulo(numero=1, titulo="U", minutos=1)],
                 escenas=[Escena(id="c01_s001", capitulo=1, narracion="n", imagen_prompt="i", movimiento_prompt="m")])

def test_crear_y_cargar(raiz):
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="Roma", duracion_min=5))
    assert a.fase(pid) == Fase.GUION
    assert a.cargar_plan(pid).idea == "Roma"
    for sub in ("imagenes", "clips", "audio"):
        assert (a.ruta(pid) / sub).is_dir()
    assert not a.tiene_guion(pid)
    a.guardar_guion(pid, _guion())
    assert a.cargar_guion(pid) == _guion()
    assert a.archivo(pid, "clip", "c01_s001") == a.ruta(pid) / "clips" / "c01_s001.mp4"

def test_fase_pausa_y_listado(raiz):
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="Roma", duracion_min=5))
    a.set_fase(pid, Fase.CLIPS)
    a.pausar(pid, "presupuesto")
    assert a.pausa(pid) == "presupuesto"
    a.quitar_pausa(pid)
    assert a.pausa(pid) is None
    fila = a.listar()[0]
    assert fila["id"] == pid and fila["fase"] == "clips" and fila["idea"] == "Roma"

def test_costes(raiz):
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="x", duracion_min=1))
    a.registrar_coste(pid, "animador", "c01_s001", 0.5)
    a.registrar_coste(pid, "animador", "c01_s002", 0.25)
    a.registrar_coste(pid, "narrador", "c01_s001", 0.1)
    assert round(a.coste_total(pid), 2) == 0.85
    assert a.costes_por_agente(pid) == {"animador": 0.75, "narrador": 0.1}
    hoy = datetime.now()
    assert round(a.coste_mes(hoy.year, hoy.month), 2) == 0.85

def test_persiste_entre_instancias_y_logs(raiz):
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="x", duracion_min=1))
    a.log(pid, "director", "hola")
    b = Almacen(raiz)
    assert b.logs(pid)[0]["mensaje"] == "hola"
    assert b.fase(pid) == Fase.GUION
```

- [ ] **Step 2: Run** `pytest tests/test_almacen.py -v` → FAIL

- [ ] **Step 3: Implementar**

```python
# core/almacen.py
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from core.modelos import Fase, Guion, Plan

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proyectos(
  id TEXT PRIMARY KEY, idea TEXT, titulo TEXT, fase TEXT, pausa TEXT, creado TEXT);
CREATE TABLE IF NOT EXISTS costes(
  pid TEXT, agente TEXT, concepto TEXT, usd REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS logs(
  pid TEXT, agente TEXT, mensaje TEXT, ts TEXT);
"""
SUBCARPETAS = {"imagen": ("imagenes", ".png"), "clip": ("clips", ".mp4"), "audio": ("audio", ".mp3")}


class Almacen:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.raiz / "director.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA)

    # --- archivos
    def ruta(self, pid: str) -> Path:
        return self.raiz / pid

    def archivo(self, pid: str, clave: str, escena_id: str) -> Path:
        carpeta, ext = SUBCARPETAS[clave]
        return self.ruta(pid) / carpeta / f"{escena_id}{ext}"

    def _escribir(self, destino: Path, texto: str) -> None:
        tmp = destino.with_suffix(destino.suffix + ".tmp")
        tmp.write_text(texto, encoding="utf-8")
        tmp.replace(destino)

    def guardar_json(self, pid: str, nombre: str, datos: dict) -> None:
        self._escribir(self.ruta(pid) / nombre, json.dumps(datos, ensure_ascii=False, indent=2))

    def cargar_json(self, pid: str, nombre: str) -> dict | None:
        p = self.ruta(pid) / nombre
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # --- proyecto
    def crear_proyecto(self, plan: Plan) -> str:
        pid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        for carpeta, _ in SUBCARPETAS.values():
            (self.ruta(pid) / carpeta).mkdir(parents=True, exist_ok=True)
        self.guardar_plan(pid, plan)
        self.db.execute("INSERT INTO proyectos VALUES(?,?,?,?,?,?)",
                        (pid, plan.idea, "", Fase.GUION.value, None, datetime.now().isoformat()))
        self.db.commit()
        return pid

    def guardar_plan(self, pid: str, plan: Plan) -> None:
        self._escribir(self.ruta(pid) / "plan.json", plan.model_dump_json(indent=2))

    def cargar_plan(self, pid: str) -> Plan:
        return Plan.model_validate_json((self.ruta(pid) / "plan.json").read_text(encoding="utf-8"))

    def tiene_guion(self, pid: str) -> bool:
        return (self.ruta(pid) / "guion.json").exists()

    def guardar_guion(self, pid: str, guion: Guion) -> None:
        self._escribir(self.ruta(pid) / "guion.json", guion.model_dump_json(indent=2))
        self.db.execute("UPDATE proyectos SET titulo=? WHERE id=?", (guion.titulo, pid))
        self.db.commit()

    def cargar_guion(self, pid: str) -> Guion:
        return Guion.model_validate_json((self.ruta(pid) / "guion.json").read_text(encoding="utf-8"))

    # --- estado
    def _campo(self, pid: str, campo: str):
        fila = self.db.execute(f"SELECT {campo} FROM proyectos WHERE id=?", (pid,)).fetchone()
        if fila is None:
            raise KeyError(pid)
        return fila[0]

    def fase(self, pid: str) -> Fase:
        return Fase(self._campo(pid, "fase"))

    def set_fase(self, pid: str, fase: Fase) -> None:
        self.db.execute("UPDATE proyectos SET fase=? WHERE id=?", (fase.value, pid))
        self.db.commit()

    def pausar(self, pid: str, motivo: str) -> None:
        self.db.execute("UPDATE proyectos SET pausa=? WHERE id=?", (motivo, pid))
        self.db.commit()

    def quitar_pausa(self, pid: str) -> None:
        self.db.execute("UPDATE proyectos SET pausa=NULL WHERE id=?", (pid,))
        self.db.commit()

    def pausa(self, pid: str) -> str | None:
        return self._campo(pid, "pausa")

    def listar(self) -> list[dict]:
        filas = self.db.execute(
            "SELECT p.*, COALESCE((SELECT SUM(usd) FROM costes c WHERE c.pid=p.id),0) AS coste "
            "FROM proyectos p ORDER BY creado DESC").fetchall()
        return [dict(f) for f in filas]

    # --- costes
    def registrar_coste(self, pid: str, agente: str, concepto: str, usd: float) -> None:
        self.db.execute("INSERT INTO costes VALUES(?,?,?,?,?)",
                        (pid, agente, concepto, float(usd), datetime.now().isoformat()))
        self.db.commit()

    def coste_total(self, pid: str) -> float:
        return self.db.execute("SELECT COALESCE(SUM(usd),0) FROM costes WHERE pid=?", (pid,)).fetchone()[0]

    def costes_por_agente(self, pid: str) -> dict[str, float]:
        filas = self.db.execute("SELECT agente, SUM(usd) FROM costes WHERE pid=? GROUP BY agente", (pid,))
        return {a: round(u, 6) for a, u in filas}

    def coste_mes(self, anio: int, mes: int) -> float:
        prefijo = f"{anio:04d}-{mes:02d}"
        return self.db.execute("SELECT COALESCE(SUM(usd),0) FROM costes WHERE ts LIKE ?",
                               (prefijo + "%",)).fetchone()[0]

    # --- logs
    def log(self, pid: str, agente: str, mensaje: str) -> None:
        self.db.execute("INSERT INTO logs VALUES(?,?,?,?)", (pid, agente, mensaje, datetime.now().isoformat()))
        self.db.commit()

    def logs(self, pid: str, limite: int = 200) -> list[dict]:
        filas = self.db.execute("SELECT agente, mensaje, ts FROM logs WHERE pid=? ORDER BY ts DESC LIMIT ?",
                                (pid, limite)).fetchall()
        return [dict(f) for f in filas]
```

- [ ] **Step 4: Run** `pytest tests/test_almacen.py -v` → PASS
- [ ] **Step 5: Commit** `git commit -am "feat: almacén SQLite y disco"` (con `git add -A` antes)

---

### Task 3: Herramientas (FFmpeg, reintentos) y contrato de proveedores + simulados

**Files:**
- Create: `herramientas/__init__.py`, `herramientas/ffmpeg.py`, `herramientas/reintentos.py`, `proveedores/__init__.py`, `proveedores/base.py`, `proveedores/simulados.py`, `tests/test_herramientas.py`, `tests/test_proveedores_simulados.py`

**Interfaces:**
- Produces:
  - `herramientas.ffmpeg`: `async ejecutar(args: list[str], cwd: Path | None = None) -> None` (lanza `RuntimeError` con las últimas líneas de stderr), `async duracion(ruta: Path) -> float`.
  - `herramientas.reintentos`: `ErrorTransitorio`, `ErrorPermanente`, `async con_reintentos(fn: Callable[[], Awaitable[T]], intentos=3, base=2.0) -> T` (reintenta solo `ErrorTransitorio`).
  - `proveedores.base`: `RespuestaLLM(texto: str, coste: float)`; protocolos `LLM.completar(sistema, prompt, max_tokens=4000) -> RespuestaLLM`, `LLM.evaluar_imagen(imagen: Path, pregunta: str) -> RespuestaLLM`, `GeneradorImagen.generar(prompt, destino: Path) -> float`, `GeneradorVideo.animar(imagen: Path, prompt: str, destino: Path, segundos: float = 10.0) -> float`, `TTS.sintetizar(texto, destino: Path) -> float`, `Subidor.subir(video: Path, meta: dict, miniatura: Path, srt: Path | None) -> str`; dataclass `Proveedores(llm, supervisor, imagen, video, tts, subidor)`; `async completar_json(llm, sistema, prompt, max_tokens=4000, validar=None, intentos=3) -> tuple[dict, float]`; `ErrorJSON`.
  - Prompts llevan una línea `TAREA: <nombre>` y `PARAMS: <json>`; helper `armar_prompt(tarea: str, params: dict, cuerpo: str) -> str`.
  - `proveedores.simulados`: `LLMSimulado`, `ImagenSimulada`, `VideoSimulado`, `TTSSimulado`, `SubidorSimulado` (atributo `subidas: list`), `proveedores_simulados() -> Proveedores`.

- [ ] **Step 1: Tests (fallan)**

```python
# tests/test_herramientas.py
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
```

```python
# tests/test_proveedores_simulados.py
import json
import pytest
from PIL import Image
from herramientas.ffmpeg import duracion
from proveedores.base import completar_json, armar_prompt, RespuestaLLM, ErrorJSON
from proveedores.simulados import proveedores_simulados

async def test_simulados_generan_archivos(tmp_path):
    p = proveedores_simulados()
    img = tmp_path / "i.png"
    assert await p.imagen.generar("algo", img) == 0
    assert Image.open(img).size == (1920, 1080)
    clip = tmp_path / "c.mp4"
    await p.video.animar(img, "zoom", clip, 10)
    assert abs(await duracion(clip) - 10) < 0.2
    aud = tmp_path / "a.mp3"
    await p.tts.sintetizar(" ".join(["palabra"] * 30), aud)
    assert abs(await duracion(aud) - 12) < 0.3

class LLMGuionado:
    def __init__(self, respuestas): self.respuestas = list(respuestas); self.prompts = []
    async def completar(self, sistema, prompt, max_tokens=4000):
        self.prompts.append(prompt); return RespuestaLLM(self.respuestas.pop(0), 0.01)

async def test_completar_json_reintenta():
    llm = LLMGuionado(["no es json", "```json\n{\"a\": 1}\n```"])
    datos, coste = await completar_json(llm, "s", "p")
    assert datos == {"a": 1} and coste == pytest.approx(0.02)
    assert "no es JSON válido" in llm.prompts[1]

async def test_completar_json_validador_y_agota():
    llm = LLMGuionado(['{"n": 1}'] * 3)
    def validar(d):
        if d["n"] != 2: raise ValueError("n debe ser 2")
    with pytest.raises(ErrorJSON):
        await completar_json(llm, "s", "p", validar=validar)

async def test_llm_simulado_responde_por_tarea():
    p = proveedores_simulados()
    r = await p.llm.completar("s", armar_prompt("esquema", {"duracion_min": 2}, "..."))
    d = json.loads(r.texto)
    assert sum(c["minutos"] for c in d["capitulos"]) == 2
```

- [ ] **Step 2: Run** `pytest tests/test_herramientas.py tests/test_proveedores_simulados.py -v` → FAIL

- [ ] **Step 3: Implementar herramientas**

```python
# herramientas/ffmpeg.py
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
```

```python
# herramientas/reintentos.py
import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class ErrorTransitorio(Exception):
    """Red, 429, 5xx: merece reintento."""


class ErrorPermanente(Exception):
    """Petición inválida, contenido rechazado: no reintentar."""


async def con_reintentos(fn: Callable[[], Awaitable[T]], intentos: int = 3, base: float = 2.0) -> T:
    for i in range(intentos):
        try:
            return await fn()
        except ErrorTransitorio:
            if i == intentos - 1:
                raise
            await asyncio.sleep(base * (2 ** i))
    raise AssertionError("inalcanzable")
```

- [ ] **Step 4: Implementar `proveedores/base.py`**

```python
# proveedores/base.py
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
```

- [ ] **Step 5: Implementar `proveedores/simulados.py`**

```python
# proveedores/simulados.py
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
```

- [ ] **Step 6: Run** `pytest tests/test_herramientas.py tests/test_proveedores_simulados.py -v` → PASS
- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: herramientas ffmpeg/reintentos y proveedores simulados"`

---

### Task 4: Estimador de costes

**Files:**
- Create: `core/costes.py`, `tests/test_costes.py`

**Interfaces:**
- Consumes: `Plan`.
- Produces: `PRECIOS: dict` y `estimar(plan: Plan, precios: dict = PRECIOS) -> dict[str, float]` con claves `guion, imagenes, clips, audio, publicacion, total`; `precio_unitario(clave: str, plan: Plan, precios=PRECIOS) -> float` para clave ∈ `imagen|clip|audio` (audio = coste por escena).

- [ ] **Step 1: Test (falla)**

```python
# tests/test_costes.py
from core.costes import estimar, precio_unitario, PRECIOS
from core.modelos import Plan

def test_estimar_20_min_barato():
    e = estimar(Plan(idea="x", duracion_min=20, modelo_video="barato"))
    assert e["clips"] == round(100 * PRECIOS["clip"]["barato"], 2)
    assert e["imagenes"] == round(100 * PRECIOS["imagen"], 2)
    assert e["total"] == round(sum(v for k, v in e.items() if k != "total"), 2)

def test_premium_mas_caro_y_unitario():
    p = Plan(idea="x", duracion_min=5, modelo_video="premium")
    assert estimar(p)["clips"] > estimar(Plan(idea="x", duracion_min=5))["clips"]
    assert precio_unitario("clip", p) == PRECIOS["clip"]["premium"]
    assert precio_unitario("audio", p) == round(PRECIOS["tts_por_minuto"] / 5, 4)
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# core/costes.py
"""Precios orientativos en USD. VERIFICAR con las webs de cada proveedor antes de producción."""
from core.modelos import ESCENAS_POR_MINUTO, Plan

PRECIOS = {
    "guion_por_minuto": 0.05,       # Claude, esquema + narración + desglose
    "imagen": 0.025,                # Flux dev 1920x1080
    "clip": {"barato": 0.30, "premium": 1.00},   # clip 10 s
    "tts_por_minuto": 0.30,
    "publicacion": 0.20,            # metadatos + 3 miniaturas
}


def precio_unitario(clave: str, plan: Plan, precios: dict = PRECIOS) -> float:
    if clave == "imagen":
        return precios["imagen"]
    if clave == "clip":
        return precios["clip"][plan.modelo_video]
    if clave == "audio":
        return round(precios["tts_por_minuto"] / ESCENAS_POR_MINUTO, 4)
    raise KeyError(clave)


def estimar(plan: Plan, precios: dict = PRECIOS) -> dict[str, float]:
    n = plan.num_escenas
    e = {
        "guion": plan.duracion_min * precios["guion_por_minuto"],
        "imagenes": n * precios["imagen"],
        "clips": n * precios["clip"][plan.modelo_video],
        "audio": plan.duracion_min * precios["tts_por_minuto"],
        "publicacion": precios["publicacion"],
    }
    e = {k: round(v, 2) for k, v in e.items()}
    e["total"] = round(sum(e.values()), 2)
    return e
```

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: estimador de costes"`

---

### Task 5: Contexto, bus de eventos, base de agentes y Guionista

**Files:**
- Create: `director/__init__.py`, `director/eventos.py`, `director/contexto.py`, `agentes/__init__.py`, `agentes/base.py`, `agentes/guionista.py`, `tests/test_guionista.py`

**Interfaces:**
- Consumes: `Almacen`, `Proveedores`, `completar_json`, `armar_prompt`, `con_reintentos`, `precio_unitario`.
- Produces:
  - `director.eventos.Bus`: `suscribir(pid) -> asyncio.Queue`, `desuscribir(pid, cola)`, `emitir(pid, evento: dict)`.
  - `director.contexto.PresupuestoAgotado(Exception)`; `Contexto(almacen, proveedores, pid, bus, concurrencia=6)` con `plan` (propiedad, recarga), `emitir(agente, mensaje, **extra)` (log + bus), `reservar(usd)` (lanza `PresupuestoAgotado` si `coste_total + reservado + usd > plan.presupuesto_max`), `liberar(usd)`, `cobrar(agente, concepto, usd)`.
  - `agentes.base.Resultado(ok: bool, errores: list[str], coste: float)`; `async procesar_escenas(ctx, agente: str, clave: str, trabajo: Callable[[Escena, Guion], Awaitable[float]], solo: list[str] | None = None, requiere: str | None = None) -> Resultado`. Selecciona escenas con `estado[clave] != GENERADO` o archivo ausente (o las de `solo`). Si `requiere` (clave previa) no está generada para esa escena → error de escena, sin llamada.
  - `agentes.guionista.Guionista` con `nombre = "guionista"`, `async ejecutar(ctx) -> Resultado`, `async regenerar_escena(ctx, escena_id, motivo="") -> None`, `async regenerar_capitulo(ctx, numero) -> None`.

- [ ] **Step 1: Test (falla)**

```python
# tests/test_guionista.py
import json
import pytest
from core.almacen import Almacen
from core.modelos import Plan
from director.contexto import Contexto
from director.eventos import Bus
from proveedores.base import RespuestaLLM
from proveedores.simulados import proveedores_simulados, LLMSimulado
from agentes.guionista import Guionista

def _ctx(raiz, duracion=2, llm=None):
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="Roma", duracion_min=duracion))
    prov = proveedores_simulados()
    if llm:
        prov.llm = llm
    return Contexto(a, prov, pid, Bus())

async def test_genera_5_escenas_por_minuto(raiz):
    ctx = _ctx(raiz, 3)
    r = await Guionista().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert r.ok and len(g.escenas) == 15
    assert len({e.id for e in g.escenas}) == 15
    assert g.escenas[0].id == "c01_s001"

class LLMEscenasCortas(LLMSimulado):
    """La primera vez que pide escenas devuelve una de menos."""
    def __init__(self): self.fallado = False
    async def completar(self, sistema, prompt, max_tokens=4000):
        r = await super().completar(sistema, prompt, max_tokens)
        if "TAREA: escenas" in prompt and not self.fallado:
            self.fallado = True
            d = json.loads(r.texto); d["escenas"] = d["escenas"][:-1]
            return RespuestaLLM(json.dumps(d), 0.0)
        return r

async def test_corrige_numero_de_escenas(raiz):
    ctx = _ctx(raiz, 1, LLMEscenasCortas())
    await Guionista().ejecutar(ctx)
    assert len(ctx.almacen.cargar_guion(ctx.pid).escenas) == 5

async def test_regenerar_escena_conserva_id_y_resetea_estado(raiz):
    ctx = _ctx(raiz, 1)
    gu = Guionista()
    await gu.ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[2].estado["imagen"] = "generado"
    ctx.almacen.guardar_guion(ctx.pid, g)
    await gu.regenerar_escena(ctx, "c01_s003")
    e = ctx.almacen.cargar_guion(ctx.pid).escena("c01_s003")
    assert e.narracion.startswith("nueva") and e.estado["imagen"] == "pendiente"

def test_reparto_de_escenas_por_capitulo():
    from agentes.guionista import repartir
    assert repartir([1.5, 1.5, 2], 25) == [8, 7, 10] or sum(repartir([1.5, 1.5, 2], 25)) == 25
    assert sum(repartir([3, 3, 3], 50)) == 50
```

- [ ] **Step 2: Run** `pytest tests/test_guionista.py -v` → FAIL

- [ ] **Step 3: Implementar eventos y contexto**

```python
# director/eventos.py
import asyncio
from collections import defaultdict


class Bus:
    def __init__(self):
        self._colas: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def suscribir(self, pid: str) -> asyncio.Queue:
        cola: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._colas[pid].add(cola)
        return cola

    def desuscribir(self, pid: str, cola: asyncio.Queue) -> None:
        self._colas[pid].discard(cola)

    def emitir(self, pid: str, evento: dict) -> None:
        for cola in list(self._colas[pid]):
            if not cola.full():
                cola.put_nowait(evento)
```

```python
# director/contexto.py
from core.almacen import Almacen
from core.modelos import Plan
from director.eventos import Bus
from proveedores.base import Proveedores


class PresupuestoAgotado(Exception):
    pass


class Contexto:
    def __init__(self, almacen: Almacen, proveedores: Proveedores, pid: str, bus: Bus, concurrencia: int = 6):
        self.almacen, self.proveedores, self.pid, self.bus = almacen, proveedores, pid, bus
        self.concurrencia = concurrencia
        self._reservado = 0.0

    @property
    def plan(self) -> Plan:
        return self.almacen.cargar_plan(self.pid)

    def emitir(self, agente: str, mensaje: str, **extra) -> None:
        self.almacen.log(self.pid, agente, mensaje)
        self.bus.emitir(self.pid, {"agente": agente, "mensaje": mensaje, **extra})

    def reservar(self, usd: float) -> None:
        tope = self.plan.presupuesto_max
        gastado = self.almacen.coste_total(self.pid)
        if gastado + self._reservado + usd > tope + 1e-9:
            raise PresupuestoAgotado(f"Presupuesto agotado: gastado {gastado:.2f} $ de {tope:.2f} $")
        self._reservado += usd

    def liberar(self, usd: float) -> None:
        self._reservado = max(0.0, self._reservado - usd)

    def cobrar(self, agente: str, concepto: str, usd: float) -> None:
        if usd:
            self.almacen.registrar_coste(self.pid, agente, concepto, usd)
```

- [ ] **Step 4: Implementar `agentes/base.py`**

```python
# agentes/base.py
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from core.costes import precio_unitario
from core.modelos import Escena, Estado, Guion
from director.contexto import Contexto, PresupuestoAgotado
from herramientas.reintentos import con_reintentos


@dataclass
class Resultado:
    ok: bool
    errores: list[str] = field(default_factory=list)
    coste: float = 0.0


def _necesita(ctx: Contexto, e: Escena, clave: str) -> bool:
    return e.estado[clave] != Estado.GENERADO or not ctx.almacen.archivo(ctx.pid, clave, e.id).exists()


async def procesar_escenas(ctx: Contexto, agente: str, clave: str,
                           trabajo: Callable[[Escena, Guion], Awaitable[float]],
                           solo: list[str] | None = None, requiere: str | None = None) -> Resultado:
    guion = ctx.almacen.cargar_guion(ctx.pid)
    objetivo = [e for e in guion.escenas if (e.id in solo if solo else _necesita(ctx, e, clave))]
    estimado = precio_unitario(clave, ctx.plan)
    sem = asyncio.Semaphore(ctx.concurrencia)
    res = Resultado(ok=True)
    hechas = 0

    async def una(e: Escena) -> None:
        nonlocal hechas
        async with sem:
            if requiere and not ctx.almacen.archivo(ctx.pid, requiere, e.id).exists():
                e.estado[clave], e.error = Estado.ERROR, f"falta {requiere}"
                res.errores.append(f"{e.id}: falta {requiere}")
                return
            ctx.reservar(estimado)
            try:
                coste = await con_reintentos(lambda: trabajo(e, guion))
                ctx.cobrar(agente, e.id, coste)
                res.coste += coste
                e.estado[clave], e.error = Estado.GENERADO, None
            except Exception as ex:  # noqa: BLE001 — se registra por escena y se sigue
                e.estado[clave], e.error = Estado.ERROR, str(ex)[:300]
                res.errores.append(f"{e.id}: {ex}")
            finally:
                ctx.liberar(estimado)
                ctx.almacen.guardar_guion(ctx.pid, guion)
                hechas += 1
                ctx.emitir(agente, f"{e.id} {e.estado[clave].value}", hechas=hechas, total=len(objetivo))

    resultados = await asyncio.gather(*(una(e) for e in objetivo), return_exceptions=True)
    for r in resultados:
        if isinstance(r, PresupuestoAgotado):
            raise r
        if isinstance(r, BaseException):
            raise r
    res.ok = not res.errores
    return res
```

- [ ] **Step 5: Implementar `agentes/guionista.py`**

```python
# agentes/guionista.py
from core.modelos import (CLAVES, ESCENAS_POR_MINUTO, PALABRAS_POR_SEGUNDO, SEGUNDOS_POR_ESCENA,
                          Capitulo, Escena, Estado, Guion)
from agentes.base import Resultado
from director.contexto import Contexto
from proveedores.base import armar_prompt, completar_json

SISTEMA = ("Eres guionista de documentales faceless para YouTube. Escribes en español, con ritmo, "
           "datos concretos y ganchos de retención. Respondes SOLO con JSON válido.")


def repartir(minutos: list[float], total: int) -> list[int]:
    """Reparte `total` escenas proporcionalmente a los minutos (mayor resto)."""
    suma = sum(minutos)
    exactos = [m / suma * total for m in minutos]
    base = [int(x) for x in exactos]
    restos = sorted(range(len(minutos)), key=lambda i: exactos[i] - base[i], reverse=True)
    for i in restos[: total - sum(base)]:
        base[i] += 1
    return [max(1, b) for b in base]


class Guionista:
    nombre = "guionista"

    async def ejecutar(self, ctx: Contexto) -> Resultado:
        plan = ctx.plan
        coste = 0.0

        def validar_esquema(d):
            assert d["titulo"] and d["capitulos"], "faltan titulo/capitulos"
            for c in d["capitulos"]:
                float(c["minutos"]); c["titulo"]

        esquema, c = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("esquema", {
            "duracion_min": plan.duracion_min}, (
            f"Idea: {plan.idea}\nTono: {plan.tono}\nAudiencia: {plan.audiencia}\nÁngulo: {plan.angulo}\n"
            f"Duración total: {plan.duracion_min} min. Diseña entre 1 y 12 capítulos cuya suma de minutos sea "
            f"{plan.duracion_min}. Incluye un gancho de 30 s y una biblia visual (estilo base: {plan.estilo_visual}; "
            "paleta, época, personajes recurrentes). JSON: "
            '{"titulo":str,"gancho":str,"biblia_visual":str,"capitulos":[{"numero":int,"titulo":str,"minutos":float}]}')),
            validar=validar_esquema)
        coste += c
        ctx.emitir(self.nombre, f"esquema: {len(esquema['capitulos'])} capítulos")

        capitulos = [Capitulo(numero=i + 1, titulo=x["titulo"], minutos=float(x["minutos"]))
                     for i, x in enumerate(esquema["capitulos"])]
        cuotas = repartir([x.minutos for x in capitulos], plan.num_escenas)
        escenas: list[Escena] = []
        resumen_previo = esquema["gancho"]
        for cap, n in zip(capitulos, cuotas):
            nuevas, c = await self._capitulo(ctx, esquema, cap, n, resumen_previo, len(escenas))
            coste += c
            escenas += nuevas
            resumen_previo = " ".join(e.narracion for e in nuevas)[-1500:]
            ctx.emitir(self.nombre, f"capítulo {cap.numero}/{len(capitulos)} listo", hechas=cap.numero,
                       total=len(capitulos))

        guion = Guion(titulo=esquema["titulo"], gancho=esquema["gancho"], biblia_visual=esquema["biblia_visual"],
                      capitulos=capitulos, escenas=escenas)
        ctx.almacen.guardar_guion(ctx.pid, guion)
        ctx.cobrar(self.nombre, "guion", coste)
        return Resultado(ok=True, coste=coste)

    async def _capitulo(self, ctx, esquema, cap: Capitulo, n: int, previo: str, offset: int):
        palabras = int(n * SEGUNDOS_POR_ESCENA * PALABRAS_POR_SEGUNDO)
        narr, c1 = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("narracion", {
            "palabras": palabras}, (
            f"Vídeo: {esquema['titulo']}\nCapítulo {cap.numero}: {cap.titulo}\n"
            f"Final de lo narrado antes (no lo repitas): {previo}\n"
            f"Escribe la narración de este capítulo, unas {palabras} palabras. JSON: {{\"narracion\": str}}")),
            max_tokens=8000, validar=lambda d: d["narracion"].strip() or (_ for _ in ()).throw(ValueError("vacía")))

        def validar(d):
            if len(d["escenas"]) != n:
                raise ValueError(f"se pidieron exactamente {n} escenas y llegaron {len(d['escenas'])}")
            for e in d["escenas"]:
                e["narracion"], e["imagen_prompt"], e["movimiento_prompt"]

        desg, c2 = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("escenas", {"n": n}, (
            f"Biblia visual: {esquema['biblia_visual']}\nNarración:\n{narr['narracion']}\n\n"
            f"Divide la narración en EXACTAMENTE {n} escenas consecutivas de ~{int(SEGUNDOS_POR_ESCENA)} s "
            f"(~{int(SEGUNDOS_POR_ESCENA * PALABRAS_POR_SEGUNDO)} palabras). Para cada una: narracion (texto literal), "
            "imagen_prompt (inglés, descriptivo, 16:9) y movimiento_prompt (inglés, movimiento de cámara y elementos). "
            'JSON: {"escenas":[{"narracion":str,"imagen_prompt":str,"movimiento_prompt":str}]}')),
            max_tokens=8000, validar=validar)
        escenas = [Escena(id=f"c{cap.numero:02d}_s{offset + i + 1:03d}", capitulo=cap.numero, **e)
                   for i, e in enumerate(desg["escenas"])]
        return escenas, c1 + c2

    async def regenerar_escena(self, ctx: Contexto, escena_id: str, motivo: str = "") -> None:
        guion = ctx.almacen.cargar_guion(ctx.pid)
        e = guion.escena(escena_id)
        i = guion.escenas.index(e)
        vecinas = " ".join(x.narracion for x in guion.escenas[max(0, i - 1): i + 2] if x.id != e.id)
        d, c = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("escena", {}, (
            f"Biblia visual: {guion.biblia_visual}\nContexto: {vecinas}\nEscena actual: {e.narracion}\n"
            f"Motivo de reescritura: {motivo or 'mejorar'}\nReescribe la escena (~30 palabras). "
            'JSON: {"narracion":str,"imagen_prompt":str,"movimiento_prompt":str}')))
        e.narracion, e.imagen_prompt, e.movimiento_prompt = d["narracion"], d["imagen_prompt"], d["movimiento_prompt"]
        e.estado = {k: Estado.PENDIENTE for k in CLAVES}
        e.duracion_audio = None
        ctx.almacen.guardar_guion(ctx.pid, guion)
        ctx.cobrar(self.nombre, f"regen {escena_id}", c)

    async def regenerar_capitulo(self, ctx: Contexto, numero: int) -> None:
        guion = ctx.almacen.cargar_guion(ctx.pid)
        cap = next(c for c in guion.capitulos if c.numero == numero)
        viejas = [e for e in guion.escenas if e.capitulo == numero]
        inicio = guion.escenas.index(viejas[0])
        previo = " ".join(e.narracion for e in guion.escenas[:inicio])[-1500:] or guion.gancho
        esquema = {"titulo": guion.titulo, "biblia_visual": guion.biblia_visual}
        nuevas, c = await self._capitulo(ctx, esquema, cap, len(viejas), previo, inicio)
        for vieja, nueva in zip(viejas, nuevas):
            nueva.id = vieja.id
        guion.escenas[inicio: inicio + len(viejas)] = nuevas
        ctx.almacen.guardar_guion(ctx.pid, guion)
        ctx.cobrar(self.nombre, f"regen cap {numero}", c)
```

Nota: el validador de narración con `throw` es feo; sustituir por función nombrada:
```python
def _no_vacia(d):
    if not d["narracion"].strip():
        raise ValueError("narración vacía")
```
y usar `validar=_no_vacia`. (Usar esta versión al implementar.)

Corregir también el test de `repartir` a una aserción determinista:
```python
def test_reparto_de_escenas_por_capitulo():
    from agentes.guionista import repartir
    assert repartir([1.5, 1.5, 2], 25) == [8, 7, 10]
    assert sum(repartir([3, 3, 3], 50)) == 50
```
(1.5/5·25 = 7.5, 7.5, 10 → base 7,7,10, resto 1 al primer empate → [8,7,10].)

- [ ] **Step 6: Run** `pytest tests/test_guionista.py -v` → PASS
- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: contexto, bus, base de agentes y guionista"`

---

### Task 6: Ilustrador y Animador

**Files:**
- Create: `agentes/ilustrador.py`, `agentes/animador.py`, `tests/test_ilustrador_animador.py`, `tests/ayudas.py`

**Interfaces:**
- Consumes: `procesar_escenas`, `Contexto`, `Guionista`.
- Produces: `Ilustrador.ejecutar(ctx, solo=None) -> Resultado` (escribe `imagenes/<id>.png`, prompt = `f"{e.imagen_prompt}. Visual style: {guion.biblia_visual}"`); `Animador.ejecutar(ctx, solo=None) -> Resultado` (requiere imagen; escribe `clips/<id>.mp4` de `SEGUNDOS_CLIP`). `tests/ayudas.py`: `async proyecto_con_guion(raiz, duracion=1, presupuesto=50.0) -> Contexto`.

- [ ] **Step 1: Tests (fallan)**

```python
# tests/ayudas.py
from core.almacen import Almacen
from core.modelos import Plan
from director.contexto import Contexto
from director.eventos import Bus
from proveedores.simulados import proveedores_simulados
from agentes.guionista import Guionista

async def proyecto_con_guion(raiz, duracion=1, presupuesto=50.0) -> Contexto:
    a = Almacen(raiz)
    pid = a.crear_proyecto(Plan(idea="Roma", duracion_min=duracion, presupuesto_max=presupuesto))
    ctx = Contexto(a, proveedores_simulados(), pid, Bus())
    await Guionista().ejecutar(ctx)
    return ctx
```

```python
# tests/test_ilustrador_animador.py
from core.modelos import Estado
from agentes.ilustrador import Ilustrador
from agentes.animador import Animador
from tests.ayudas import proyecto_con_guion

class ContadorImagen:
    def __init__(self, interno): self.interno, self.prompts = interno, []
    async def generar(self, prompt, destino):
        self.prompts.append(prompt); return await self.interno.generar(prompt, destino)

async def test_ilustra_todas_con_biblia(raiz):
    ctx = await proyecto_con_guion(raiz)
    cont = ContadorImagen(ctx.proveedores.imagen); ctx.proveedores.imagen = cont
    r = await Ilustrador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert r.ok and len(cont.prompts) == 5
    assert all(g.biblia_visual in p for p in cont.prompts)
    assert all(e.estado["imagen"] == Estado.GENERADO for e in g.escenas)

async def test_reanuda_sin_repetir_y_repara_faltantes(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx)
    ctx.almacen.archivo(ctx.pid, "imagen", "c01_s002").unlink()
    cont = ContadorImagen(ctx.proveedores.imagen); ctx.proveedores.imagen = cont
    await Ilustrador().ejecutar(ctx)
    assert len(cont.prompts) == 1

async def test_animador_requiere_imagen(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx, solo=["c01_s001"])
    r = await Animador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert g.escena("c01_s001").estado["clip"] == Estado.GENERADO
    assert g.escena("c01_s002").estado["clip"] == Estado.ERROR
    assert not r.ok and len(r.errores) == 4

async def test_error_en_una_escena_no_para_el_resto(raiz):
    ctx = await proyecto_con_guion(raiz)
    interno = ctx.proveedores.imagen
    class Rompe:
        async def generar(self, prompt, destino):
            if destino.stem == "c01_s003": raise ValueError("contenido rechazado")
            return await interno.generar(prompt, destino)
    ctx.proveedores.imagen = Rompe()
    r = await Ilustrador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert len(r.errores) == 1 and "rechazado" in g.escena("c01_s003").error
    assert sum(e.estado["imagen"] == Estado.GENERADO for e in g.escenas) == 4
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# agentes/ilustrador.py
from agentes.base import Resultado, procesar_escenas
from director.contexto import Contexto


class Ilustrador:
    nombre = "ilustrador"

    async def ejecutar(self, ctx: Contexto, solo: list[str] | None = None) -> Resultado:
        async def trabajo(e, guion):
            prompt = f"{e.imagen_prompt}. Visual style: {guion.biblia_visual}"
            return await ctx.proveedores.imagen.generar(prompt, ctx.almacen.archivo(ctx.pid, "imagen", e.id))
        return await procesar_escenas(ctx, self.nombre, "imagen", trabajo, solo)
```

```python
# agentes/animador.py
from agentes.base import Resultado, procesar_escenas
from core.modelos import SEGUNDOS_CLIP
from director.contexto import Contexto


class Animador:
    nombre = "animador"

    async def ejecutar(self, ctx: Contexto, solo: list[str] | None = None) -> Resultado:
        async def trabajo(e, guion):
            return await ctx.proveedores.video.animar(
                ctx.almacen.archivo(ctx.pid, "imagen", e.id), e.movimiento_prompt,
                ctx.almacen.archivo(ctx.pid, "clip", e.id), SEGUNDOS_CLIP)
        return await procesar_escenas(ctx, self.nombre, "clip", trabajo, solo, requiere="imagen")
```

- [ ] **Step 4: Run** `pytest tests/test_ilustrador_animador.py -v` → PASS
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: agentes ilustrador y animador"`

---

### Task 7: Narrador

**Files:**
- Create: `agentes/narrador.py`, `tests/test_narrador.py`

**Interfaces:**
- Produces: `Narrador.ejecutar(ctx, solo=None) -> Resultado`: escribe `audio/<id>.mp3` y guarda `Escena.duracion_audio` (ffprobe). Escenas con narración vacía → error de escena "narración vacía" sin llamada.

- [ ] **Step 1: Test (falla)**

```python
# tests/test_narrador.py
from agentes.narrador import Narrador
from tests.ayudas import proyecto_con_guion

async def test_narra_y_mide_duracion(raiz):
    ctx = await proyecto_con_guion(raiz)
    r = await Narrador().ejecutar(ctx)
    g = ctx.almacen.cargar_guion(ctx.pid)
    assert r.ok
    assert all(abs(e.duracion_audio - 12) < 0.4 for e in g.escenas)

async def test_narracion_vacia_es_error_sin_llamada(raiz):
    ctx = await proyecto_con_guion(raiz)
    g = ctx.almacen.cargar_guion(ctx.pid); g.escenas[0].narracion = "  "
    ctx.almacen.guardar_guion(ctx.pid, g)
    r = await Narrador().ejecutar(ctx)
    assert len(r.errores) == 1 and "vacía" in r.errores[0]
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# agentes/narrador.py
from agentes.base import Resultado, procesar_escenas
from director.contexto import Contexto
from herramientas.ffmpeg import duracion
from herramientas.reintentos import ErrorPermanente


class Narrador:
    nombre = "narrador"

    async def ejecutar(self, ctx: Contexto, solo: list[str] | None = None) -> Resultado:
        async def trabajo(e, guion):
            if not e.narracion.strip():
                raise ErrorPermanente("narración vacía")
            destino = ctx.almacen.archivo(ctx.pid, "audio", e.id)
            coste = await ctx.proveedores.tts.sintetizar(e.narracion, destino)
            e.duracion_audio = await duracion(destino)
            return coste
        return await procesar_escenas(ctx, self.nombre, "audio", trabajo, solo)
```

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: agente narrador"`

---

### Task 8: (fusionada en Task 9 — no existe; numeración continua abajo)

> Nota para ejecución: no hay Task 8; pasar a Task 9.

---

### Task 9: Montador

**Files:**
- Create: `agentes/montador.py`, `tests/test_montador.py`

**Interfaces:**
- Consumes: archivos `clips/`, `audio/`, `Escena.duracion_audio`.
- Produces: `Montador.ejecutar(ctx) -> Resultado` → `final.mp4`, `subtitulos.srt`, `montaje.json` = `{"duracion": float, "capitulos": [{"numero": int, "titulo": str, "inicio": float}], "avisos": [str]}`. Funciones puras: `velocidad(clip_s: float, audio_s: float) -> tuple[float, str | None]`, `generar_srt(escenas: list[Escena]) -> str`, `formato_srt(t: float) -> str`, `linea_concat(ruta: Path) -> str`.
- Requiere que todas las escenas tengan clip y audio generados; si no → `Resultado(ok=False, errores=[...])` sin montar.

- [ ] **Step 1: Tests (fallan)**

```python
# tests/test_montador.py
from pathlib import Path
from agentes.montador import Montador, velocidad, generar_srt, formato_srt, linea_concat
from agentes.ilustrador import Ilustrador
from agentes.animador import Animador
from agentes.narrador import Narrador
from core.modelos import Escena
from herramientas.ffmpeg import duracion
from tests.ayudas import proyecto_con_guion

def test_velocidad_en_rango_y_fuera():
    v, aviso = velocidad(10, 12)
    assert abs(v - 10 / 12) < 1e-6 and aviso is None
    v, aviso = velocidad(10, 30)
    assert v == 0.6 and "fuera de rango" in aviso

def test_formato_y_srt():
    assert formato_srt(3661.5) == "01:01:01,500"
    es = [Escena(id="a", capitulo=1, narracion="hola mundo", imagen_prompt="", movimiento_prompt="", duracion_audio=2.0),
          Escena(id="b", capitulo=1, narracion="adiós", imagen_prompt="", movimiento_prompt="", duracion_audio=3.0)]
    srt = generar_srt(es)
    assert "00:00:00,000 --> 00:00:02,000" in srt and "00:00:02,000 --> 00:00:05,000" in srt

def test_lista_concat_escapa_rutas():
    assert linea_concat(Path("C:/Mis vídeos/it's/seg.mp4")) == "file 'C:/Mis vídeos/it'\\''s/seg.mp4'"

async def _producido(raiz):
    ctx = await proyecto_con_guion(raiz)
    for ag in (Ilustrador(), Animador(), Narrador()):
        await ag.ejecutar(ctx)
    return ctx

async def test_monta_video_final(raiz):
    ctx = await _producido(raiz)
    r = await Montador().ejecutar(ctx)
    final = ctx.almacen.ruta(ctx.pid) / "final.mp4"
    assert r.ok and final.exists()
    assert abs(await duracion(final) - 60) < 1.5
    m = ctx.almacen.cargar_json(ctx.pid, "montaje.json")
    assert m["capitulos"][0]["inicio"] == 0
    assert (ctx.almacen.ruta(ctx.pid) / "subtitulos.srt").exists()

async def test_audio_largo_genera_aviso_y_no_falla(raiz):
    ctx = await _producido(raiz)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[0].narracion = " ".join(["larga"] * 80)          # ~32 s
    ctx.almacen.guardar_guion(ctx.pid, g)
    await Narrador().ejecutar(ctx, solo=[g.escenas[0].id])
    r = await Montador().ejecutar(ctx)
    m = ctx.almacen.cargar_json(ctx.pid, "montaje.json")
    assert r.ok and any(g.escenas[0].id in a for a in m["avisos"])

async def test_no_monta_si_faltan_piezas(raiz):
    ctx = await proyecto_con_guion(raiz)
    r = await Montador().ejecutar(ctx)
    assert not r.ok and r.errores
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# agentes/montador.py
import shutil
from pathlib import Path

from agentes.base import Resultado
from core.modelos import SEGUNDOS_CLIP, VELOCIDAD_MAX, VELOCIDAD_MIN, Escena, Estado
from director.contexto import Contexto
from herramientas.ffmpeg import duracion, ejecutar

FUNDIDO = 0.3
PALABRAS_POR_SUBTITULO = 12


def velocidad(clip_s: float, audio_s: float) -> tuple[float, str | None]:
    v = clip_s / audio_s
    if VELOCIDAD_MIN <= v <= VELOCIDAD_MAX:
        return v, None
    acotada = min(max(v, VELOCIDAD_MIN), VELOCIDAD_MAX)
    return acotada, f"velocidad {v:.2f}x fuera de rango, se usa {acotada:.2f}x y se rellena/recorta"


def formato_srt(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generar_srt(escenas: list[Escena]) -> str:
    bloques, t, n = [], 0.0, 1
    for e in escenas:
        palabras = e.narracion.split()
        trozos = [palabras[i:i + PALABRAS_POR_SUBTITULO] for i in range(0, len(palabras), PALABRAS_POR_SUBTITULO)] or [[]]
        paso = e.duracion_audio / len(trozos)
        for i, trozo in enumerate(trozos):
            ini, fin = t + i * paso, t + (i + 1) * paso
            bloques.append(f"{n}\n{formato_srt(ini)} --> {formato_srt(fin)}\n{' '.join(trozo)}\n")
            n += 1
        t += e.duracion_audio
    return "\n".join(bloques)


def linea_concat(ruta: Path) -> str:
    return "file '" + ruta.as_posix().replace("'", "'\\''") + "'"


class Montador:
    nombre = "montador"

    async def ejecutar(self, ctx: Contexto) -> Resultado:
        guion, plan = ctx.almacen.cargar_guion(ctx.pid), ctx.plan
        base = ctx.almacen.ruta(ctx.pid)
        faltan = [e.id for e in guion.escenas
                  if e.estado["clip"] != Estado.GENERADO or e.estado["audio"] != Estado.GENERADO]
        if faltan:
            return Resultado(ok=False, errores=[f"faltan clip/audio en: {', '.join(faltan[:10])}"])

        segs = base / "segmentos"
        segs.mkdir(exist_ok=True)
        avisos, lineas = [], []
        for i, e in enumerate(guion.escenas, 1):
            clip = ctx.almacen.archivo(ctx.pid, "clip", e.id)
            audio = ctx.almacen.archivo(ctx.pid, "audio", e.id)
            a = e.duracion_audio or await duracion(audio)
            v, aviso = velocidad(SEGUNDOS_CLIP, a)
            if aviso:
                avisos.append(f"{e.id}: {aviso}")
            filtro = (f"[0:v]setpts=PTS/{v:.5f},scale=1920:1080:force_original_aspect_ratio=increase,"
                      f"crop=1920:1080,fps=30,tpad=stop_mode=clone:stop_duration={a:.3f},trim=duration={a:.3f},"
                      f"fade=t=in:st=0:d={FUNDIDO},fade=t=out:st={max(0, a - FUNDIDO):.3f}:d={FUNDIDO},"
                      f"setsar=1,format=yuv420p[v]")
            destino = segs / f"{e.id}.mp4"
            await ejecutar(["-i", str(clip), "-i", str(audio), "-filter_complex", filtro,
                            "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", f"{a:.3f}", str(destino)])
            lineas.append(linea_concat(destino.resolve()))
            ctx.emitir(self.nombre, f"segmento {e.id}", hechas=i, total=len(guion.escenas))

        lista = base / "lista.txt"
        lista.write_text("\n".join(lineas), encoding="utf-8")
        unido = base / "unido.mp4"
        await ejecutar(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(unido)])

        srt = base / "subtitulos.srt"
        srt.write_text(generar_srt(guion.escenas), encoding="utf-8")
        final = base / "final.mp4"
        await self._mezcla_final(unido, final, plan.musica, srt if plan.subtitulos_incrustados else None, base)

        inicios, t = {}, 0.0
        for e in guion.escenas:
            inicios.setdefault(e.capitulo, t)
            t += e.duracion_audio
        ctx.almacen.guardar_json(ctx.pid, "montaje.json", {
            "duracion": t, "avisos": avisos,
            "capitulos": [{"numero": c.numero, "titulo": c.titulo, "inicio": round(inicios.get(c.numero, 0), 2)}
                          for c in guion.capitulos]})
        shutil.rmtree(segs, ignore_errors=True)
        unido.unlink(missing_ok=True)
        ctx.emitir(self.nombre, f"final.mp4 listo ({t / 60:.1f} min, {len(avisos)} avisos)")
        return Resultado(ok=True)

    async def _mezcla_final(self, unido: Path, final: Path, musica: str | None, srt: Path | None, base: Path):
        if not musica and not srt:
            unido.replace(final)
            return
        args = ["-i", str(unido)]
        vfiltro = "[0:v]copy[v]"
        if srt:
            vfiltro = f"[0:v]subtitles={srt.name}[v]"   # cwd=base evita escapar rutas de Windows
        if musica:
            args += ["-stream_loop", "-1", "-i", str(Path(musica).resolve())]
            afiltro = ("[1:a]volume=0.25[m];[m][0:a]sidechaincompress=threshold=0.05:ratio=8[d];"
                       "[0:a][d]amix=inputs=2:duration=first[a]")
        else:
            afiltro = "[0:a]anull[a]"
        vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"] if srt else ["-c:v", "copy"]
        if not srt:
            args += ["-filter_complex", afiltro, "-map", "0:v", "-map", "[a]"]
        else:
            args += ["-filter_complex", f"{vfiltro};{afiltro}", "-map", "[v]", "-map", "[a]"]
        await ejecutar([*args, *vcodec, "-c:a", "aac", "-shortest", str(final.resolve())], cwd=base)
```

- [ ] **Step 4: Run** `pytest tests/test_montador.py -v` → PASS
- [ ] **Step 5: Añadir test de música/subtítulos incrustados**

```python
async def test_musica_y_subtitulos_incrustados(raiz):
    from herramientas.ffmpeg import ejecutar
    ctx = await _producido(raiz)
    musica = raiz / "música.mp3"
    await ejecutar(["-f", "lavfi", "-i", "sine=frequency=440", "-t", "5", str(musica)])
    plan = ctx.plan; plan.musica = str(musica); plan.subtitulos_incrustados = True
    ctx.almacen.guardar_plan(ctx.pid, plan)
    r = await Montador().ejecutar(ctx)
    assert r.ok and abs(await duracion(ctx.almacen.ruta(ctx.pid) / "final.mp4") - 60) < 1.5
```
Run → PASS (si falla el filtro `subtitles`, comprobar que el build de FFmpeg incluye libass: `ffmpeg -filters | findstr subtitles`).

- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: agente montador"`

---

### Task 10: Publicador

**Files:**
- Create: `agentes/publicador.py`, `tests/test_publicador.py`

**Interfaces:**
- Consumes: `montaje.json`, `final.mp4`, `subtitulos.srt`, `Proveedores.llm/imagen/subidor`.
- Produces: `Publicador.preparar(ctx) -> Resultado` → `publicacion.json`:
  `{"titulos": [str]*3, "descripcion": str, "etiquetas": [str], "miniaturas": [str]*3 (rutas relativas al proyecto), "titulo_elegido": None, "miniatura_elegida": None, "privacidad": "private", "publicar_en": None, "video_id": None}`; miniaturas `miniatura_1..3.png` 1280×720 con texto. `Publicador.subir(ctx) -> Resultado` (exige `titulo_elegido` y `miniatura_elegida`; guarda `video_id`). Funciones: `marcas_capitulos(capitulos: list[dict]) -> str` (`"00:00 Título"`, formato `H:MM:SS` si ≥1 h).

- [ ] **Step 1: Test (falla)**

```python
# tests/test_publicador.py
import pytest
from PIL import Image
from agentes.publicador import Publicador, marcas_capitulos
from tests.test_montador import _producido
from agentes.montador import Montador

def test_marcas_capitulos():
    t = marcas_capitulos([{"titulo": "Inicio", "inicio": 0}, {"titulo": "Caída", "inicio": 3725.2}])
    assert t == "00:00 Inicio\n1:02:05 Caída"

async def test_preparar_y_subir(raiz):
    ctx = await _producido(raiz)
    await Montador().ejecutar(ctx)
    pub = Publicador()
    r = await pub.preparar(ctx)
    d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
    assert r.ok and len(d["titulos"]) == 3 and len(d["miniaturas"]) == 3
    assert "00:00" in d["descripcion"]
    assert Image.open(ctx.almacen.ruta(ctx.pid) / d["miniaturas"][0]).size == (1280, 720)
    r = await pub.subir(ctx)
    assert not r.ok                                   # falta elección
    d["titulo_elegido"], d["miniatura_elegida"] = d["titulos"][1], d["miniaturas"][2]
    ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
    r = await pub.subir(ctx)
    sub = ctx.proveedores.subidor.subidas[0]
    assert r.ok and sub["meta"]["titulo"] == d["titulos"][1]
    assert ctx.almacen.cargar_json(ctx.pid, "publicacion.json")["video_id"] == "SIMULADO123"
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# agentes/publicador.py
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agentes.base import Resultado
from core.costes import PRECIOS
from director.contexto import Contexto
from herramientas.reintentos import con_reintentos
from proveedores.base import armar_prompt, completar_json

SISTEMA = "Eres experto en SEO y CTR de YouTube en español. Respondes SOLO con JSON válido."


def _hms(t: float) -> str:
    t = int(t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def marcas_capitulos(capitulos: list[dict]) -> str:
    return "\n".join(f"{_hms(c['inicio'])} {c['titulo']}" for c in capitulos)


def _rotular(ruta: Path, texto: str) -> None:
    img = Image.open(ruta).convert("RGB").resize((1280, 720))
    d = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("arialbd.ttf", 96)
    except OSError:
        fuente = ImageFont.load_default()
    x, y = 60, 720 - 200
    d.text((x, y), texto.upper(), font=fuente, fill="white", stroke_width=8, stroke_fill="black")
    img.save(ruta)


class Publicador:
    nombre = "publicador"

    async def preparar(self, ctx: Contexto) -> Resultado:
        guion, plan = ctx.almacen.cargar_guion(ctx.pid), ctx.plan
        montaje = ctx.almacen.cargar_json(ctx.pid, "montaje.json")

        def validar(d):
            if len(d["titulos"]) != 3 or len(d["miniatura_prompts"]) != 3:
                raise ValueError("se necesitan 3 títulos y 3 miniatura_prompts")
            d["descripcion"], d["etiquetas"], d["texto_miniatura"]

        resumen = " ".join(e.narracion for e in guion.escenas)[:6000]
        meta, coste = await completar_json(ctx.proveedores.llm, SISTEMA, armar_prompt("metadatos", {}, (
            f"Título de trabajo: {guion.titulo}\nAudiencia: {plan.audiencia}\nÁngulo: {plan.angulo}\n"
            f"Estilo visual: {guion.biblia_visual}\nGuion (extracto): {resumen}\n"
            "Genera 3 títulos (≤70 caracteres), descripción (2-3 párrafos, sin marcas de tiempo), 10-15 etiquetas, "
            "texto_miniatura (≤4 palabras) y 3 miniatura_prompts (inglés, 16:9, alto contraste, sin texto). JSON: "
            '{"titulos":[str],"descripcion":str,"etiquetas":[str],"texto_miniatura":str,"miniatura_prompts":[str]}')),
            validar=validar)
        base = ctx.almacen.ruta(ctx.pid)
        miniaturas = []
        for i, p in enumerate(meta["miniatura_prompts"], 1):
            ruta = base / f"miniatura_{i}.png"
            coste += await con_reintentos(lambda: ctx.proveedores.imagen.generar(
                f"{p}. Visual style: {guion.biblia_visual}", ruta))
            _rotular(ruta, meta["texto_miniatura"])
            miniaturas.append(ruta.name)
        descripcion = f"{meta['descripcion']}\n\nCapítulos:\n{marcas_capitulos(montaje['capitulos'])}"
        ctx.almacen.guardar_json(ctx.pid, "publicacion.json", {
            "titulos": meta["titulos"], "descripcion": descripcion, "etiquetas": meta["etiquetas"],
            "miniaturas": miniaturas, "titulo_elegido": None, "miniatura_elegida": None,
            "privacidad": "private", "publicar_en": None, "video_id": None})
        ctx.cobrar(self.nombre, "metadatos+miniaturas", coste)
        ctx.emitir(self.nombre, "metadatos y miniaturas listos")
        return Resultado(ok=True, coste=coste)

    async def subir(self, ctx: Contexto) -> Resultado:
        d = ctx.almacen.cargar_json(ctx.pid, "publicacion.json")
        if not d or not d.get("titulo_elegido") or not d.get("miniatura_elegida"):
            return Resultado(ok=False, errores=["elige título y miniatura antes de publicar"])
        base = ctx.almacen.ruta(ctx.pid)
        meta = {"titulo": d["titulo_elegido"], "descripcion": d["descripcion"], "etiquetas": d["etiquetas"],
                "privacidad": d["privacidad"], "publicar_en": d["publicar_en"]}
        video_id = await con_reintentos(lambda: ctx.proveedores.subidor.subir(
            base / "final.mp4", meta, base / d["miniatura_elegida"], base / "subtitulos.srt"))
        d["video_id"] = video_id
        ctx.almacen.guardar_json(ctx.pid, "publicacion.json", d)
        ctx.emitir(self.nombre, f"subido a YouTube: {video_id}")
        return Resultado(ok=True)
```
(`PRECIOS` import no usado — omitirlo al implementar.)

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: agente publicador"`

---

### Task 11: Arquitecto

**Files:**
- Create: `arquitecto/__init__.py`, `arquitecto/arquitecto.py`, `tests/test_arquitecto.py`

**Interfaces:**
- Consumes: `Proveedores.supervisor`, `Almacen`, `Contexto`, `MAX_REGENERACIONES`.
- Produces: `Arquitecto` con:
  - `async planificar(supervisor: LLM, idea: str, duracion_min: int, tono: str, presupuesto_max: float) -> tuple[Plan, float]` (respeta `duracion_min`, `tono`, `presupuesto_max` del usuario).
  - `async revisar_guion(ctx) -> list[tuple[str, str]]` (id, motivo): reglas deterministas (palabras <10 o >45 por escena) + revisión LLM de repeticiones (`TAREA: revision_guion`, respuesta `{"regenerar":[{"id","motivo"}]}`). Filtra escenas con `regeneraciones >= MAX_REGENERACIONES`.
  - `async revisar_imagenes(ctx, muestra: int = 8) -> list[tuple[str, str]]` (evalúa con `supervisor.evaluar_imagen`, respuesta `{"ok": bool, "motivo": str}`).
  - `async revisar_clips(ctx) -> list[tuple[str, str]]` (clip con duración < 9 s o ilegible).
  - `marcar_regeneracion(ctx, ids: list[str]) -> None` (incrementa `regeneraciones`).
  - `informe(ctx) -> Path` → `informe.md`.

- [ ] **Step 1: Test (falla)**

```python
# tests/test_arquitecto.py
import json
from arquitecto.arquitecto import Arquitecto
from agentes.ilustrador import Ilustrador
from agentes.animador import Animador
from core.modelos import MAX_REGENERACIONES
from proveedores.base import RespuestaLLM
from proveedores.simulados import LLMSimulado
from tests.ayudas import proyecto_con_guion

async def test_planificar_respeta_usuario():
    plan, _ = await Arquitecto().planificar(LLMSimulado(), "Roma", 20, "épico", 80.0)
    assert (plan.duracion_min, plan.tono, plan.presupuesto_max) == (20, "épico", 80.0)
    assert plan.estilo_visual and plan.audiencia

async def test_revisar_guion_detecta_escena_corta_y_limita(raiz):
    ctx = await proyecto_con_guion(raiz)
    g = ctx.almacen.cargar_guion(ctx.pid)
    g.escenas[1].narracion = "muy corta"
    g.escenas[2].narracion = "corta también"; g.escenas[2].regeneraciones = MAX_REGENERACIONES
    ctx.almacen.guardar_guion(ctx.pid, g)
    ids = [i for i, _ in await Arquitecto().revisar_guion(ctx)]
    assert ids == [g.escenas[1].id]

async def test_revisar_imagenes_usa_supervisor(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx)
    class Exigente(LLMSimulado):
        async def evaluar_imagen(self, imagen, pregunta):
            return RespuestaLLM(json.dumps({"ok": imagen.stem != "c01_s001", "motivo": "incoherente"}), 0.01)
    ctx.proveedores.supervisor = Exigente()
    malas = await Arquitecto().revisar_imagenes(ctx, muestra=10)
    assert malas == [("c01_s001", "incoherente")]

async def test_revisar_clips_y_informe(raiz):
    ctx = await proyecto_con_guion(raiz)
    await Ilustrador().ejecutar(ctx); await Animador().ejecutar(ctx)
    assert await Arquitecto().revisar_clips(ctx) == []
    ruta = Arquitecto().informe(ctx)
    assert "Coste total" in ruta.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# arquitecto/arquitecto.py
import random
from datetime import datetime
from pathlib import Path

from core.modelos import MAX_REGENERACIONES, Estado, Plan
from director.contexto import Contexto
from herramientas.ffmpeg import duracion
from proveedores.base import LLM, armar_prompt, completar_json

SISTEMA = ("Eres el Arquitecto de una productora de documentales faceless para YouTube: planificas, "
           "supervisas la calidad y cuidas el presupuesto. Respondes SOLO con JSON válido.")


class Arquitecto:
    nombre = "arquitecto"

    async def planificar(self, supervisor: LLM, idea: str, duracion_min: int, tono: str,
                         presupuesto_max: float) -> tuple[Plan, float]:
        d, coste = await completar_json(supervisor, SISTEMA, armar_prompt("plan", {}, (
            f"Idea: {idea}\nDuración: {duracion_min} min\nTono: {tono}\nPresupuesto: {presupuesto_max} $\n"
            "Define estilo_visual (inglés, para prompts de imagen), audiencia, angulo (enfoque narrativo) y "
            "modelo_video ('barato' o 'premium', según presupuesto). JSON: "
            '{"estilo_visual":str,"audiencia":str,"angulo":str,"modelo_video":str}')))
        plan = Plan(idea=idea, duracion_min=duracion_min, tono=tono, presupuesto_max=presupuesto_max,
                    estilo_visual=d.get("estilo_visual") or Plan.model_fields["estilo_visual"].default,
                    audiencia=d.get("audiencia", ""), angulo=d.get("angulo", ""),
                    modelo_video=d.get("modelo_video") if d.get("modelo_video") in ("barato", "premium") else "barato")
        return plan, coste

    def _filtrar(self, ctx: Contexto, candidatos: list[tuple[str, str]]) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        vistos, salida = set(), []
        for i, m in candidatos:
            try:
                e = g.escena(i)
            except KeyError:
                continue
            if i not in vistos and e.regeneraciones < MAX_REGENERACIONES:
                vistos.add(i)
                salida.append((i, m))
        return salida

    async def revisar_guion(self, ctx: Contexto) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        candidatos = []
        for e in g.escenas:
            n = len(e.narracion.split())
            if n < 10 or n > 45:
                candidatos.append((e.id, f"{n} palabras (objetivo ~30)"))
        texto = "\n".join(f"[{e.id}] {e.narracion}" for e in g.escenas)[:60000]
        d, coste = await completar_json(ctx.proveedores.supervisor, SISTEMA, armar_prompt("revision_guion", {}, (
            f"Revisa el guion. Señala SOLO escenas con repeticiones claras, contradicciones o errores factuales "
            f"evidentes.\n{texto}\nJSON: {{\"regenerar\":[{{\"id\":str,\"motivo\":str}}]}}")), max_tokens=2000)
        candidatos += [(x["id"], x["motivo"]) for x in d.get("regenerar", [])]
        ctx.cobrar(self.nombre, "revision guion", coste)
        return self._filtrar(ctx, candidatos)

    async def revisar_imagenes(self, ctx: Contexto, muestra: int = 8) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        hechas = [e for e in g.escenas if e.estado["imagen"] == Estado.GENERADO]
        elegidas = random.sample(hechas, min(muestra, len(hechas)))
        malas, coste = [], 0.0
        for e in elegidas:
            r = await ctx.proveedores.supervisor.evaluar_imagen(
                ctx.almacen.archivo(ctx.pid, "imagen", e.id),
                f"Biblia visual: {g.biblia_visual}\nDebe mostrar: {e.imagen_prompt}\n"
                '¿Es coherente con el estilo y sin defectos graves (manos deformes, texto basura)? '
                'JSON: {"ok":bool,"motivo":str}')
            coste += r.coste
            from proveedores.base import extraer_json
            d = extraer_json(r.texto)
            if not d.get("ok", True):
                malas.append((e.id, d.get("motivo", "")))
        ctx.cobrar(self.nombre, "revision imagenes", coste)
        return self._filtrar(ctx, sorted(malas))

    async def revisar_clips(self, ctx: Contexto) -> list[tuple[str, str]]:
        g = ctx.almacen.cargar_guion(ctx.pid)
        malos = []
        for e in g.escenas:
            if e.estado["clip"] != Estado.GENERADO:
                continue
            try:
                if await duracion(ctx.almacen.archivo(ctx.pid, "clip", e.id)) < 9.0:
                    malos.append((e.id, "clip demasiado corto"))
            except Exception:  # noqa: BLE001
                malos.append((e.id, "clip ilegible"))
        return self._filtrar(ctx, malos)

    def marcar_regeneracion(self, ctx: Contexto, ids: list[str]) -> None:
        g = ctx.almacen.cargar_guion(ctx.pid)
        for i in ids:
            g.escena(i).regeneraciones += 1
        ctx.almacen.guardar_guion(ctx.pid, g)

    def informe(self, ctx: Contexto) -> Path:
        g, plan = ctx.almacen.cargar_guion(ctx.pid), ctx.plan
        costes = ctx.almacen.costes_por_agente(ctx.pid)
        montaje = ctx.almacen.cargar_json(ctx.pid, "montaje.json") or {}
        pub = ctx.almacen.cargar_json(ctx.pid, "publicacion.json") or {}
        regen = [e for e in g.escenas if e.regeneraciones]
        lineas = [f"# Informe — {g.titulo}", f"Generado: {datetime.now():%Y-%m-%d %H:%M}", "",
                  f"- Idea: {plan.idea}", f"- Duración: {montaje.get('duracion', 0) / 60:.1f} min · "
                  f"{len(g.escenas)} escenas", f"- Modelo de vídeo: {plan.modelo_video}",
                  f"- **Coste total: {ctx.almacen.coste_total(ctx.pid):.2f} $** (tope {plan.presupuesto_max:.2f} $)",
                  "", "## Coste por agente", *[f"- {a}: {u:.2f} $" for a, u in costes.items()],
                  "", "## Regeneraciones", *([f"- {e.id}: {e.regeneraciones}" for e in regen] or ["- ninguna"]),
                  "", "## Avisos de montaje", *([f"- {a}" for a in montaje.get("avisos", [])] or ["- ninguno"]),
                  "", f"## Publicación\n- Vídeo: {pub.get('video_id') or 'no publicado'}"]
        ruta = ctx.almacen.ruta(ctx.pid) / "informe.md"
        ruta.write_text("\n".join(lineas), encoding="utf-8")
        return ruta
```
(Mover `from proveedores.base import extraer_json` a la cabecera al implementar.)

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: arquitecto supervisor"`

---

### Task 12: Director (máquina de estados)

**Files:**
- Create: `director/director.py`, `tests/test_director.py`

**Interfaces:**
- Consumes: todos los agentes, `Arquitecto`, `Almacen`, `Bus`, `Contexto`, `PresupuestoAgotado`, `estimar`.
- Produces: `Director(almacen, proveedores, bus, concurrencia=6)`:
  - `async crear(idea, duracion_min, tono, presupuesto_max) -> str`
  - `async avanzar(pid) -> Fase` — ejecuta hasta un ⏸, pausa o fin; nunca pasa de `APROBACION_GUION`/`APROBACION_FINAL` por sí solo.
  - `lanzar(pid) -> None` (tarea de fondo; ignora si ya hay una en curso para ese pid) y `ocupado(pid) -> bool`.
  - `aprobar_guion(pid)`, `aprobar_final(pid, titulo, miniatura, privacidad="private", publicar_en=None)` (lanzan `ValueError` si la fase no corresponde).
  - `reanudar(pid)` (quita pausa y lanza), `cambiar_presupuesto(pid, usd)`.
  - `async regenerar(pid, escena_id, clave)` con clave ∈ `guion|imagen|clip|audio`: resetea esa clave y las dependientes (`imagen`→`clip`; `guion`→todas), ejecuta el agente con `solo=[id]`. Si la fase está en `APROBACION_FINAL`, vuelve a `MONTAJE`.
  - `async regenerar_capitulo(pid, numero)` (solo en `APROBACION_GUION`).
  - `estimacion(pid) -> dict` (de `core.costes.estimar`).

- [ ] **Step 1: Tests (fallan)**

```python
# tests/test_director.py
import pytest
from core.almacen import Almacen
from core.modelos import Fase
from director.director import Director
from director.eventos import Bus
from proveedores.simulados import proveedores_simulados
from proveedores.base import Proveedores

def _director(raiz, prov=None):
    return Director(Almacen(raiz), prov or proveedores_simulados(), Bus())

async def test_flujo_completo_con_aprobaciones(raiz):
    d = _director(raiz)
    pid = await d.crear("Roma", 1, "documental", 50)
    assert await d.avanzar(pid) == Fase.APROBACION_GUION
    assert await d.avanzar(pid) == Fase.APROBACION_GUION       # no salta el ⏸
    with pytest.raises(ValueError):
        d.aprobar_final(pid, "t", "m")
    d.aprobar_guion(pid)
    assert await d.avanzar(pid) == Fase.APROBACION_FINAL
    assert (d.almacen.ruta(pid) / "final.mp4").exists()
    pub = d.almacen.cargar_json(pid, "publicacion.json")
    d.aprobar_final(pid, pub["titulos"][0], pub["miniaturas"][0])
    assert await d.avanzar(pid) == Fase.COMPLETADO
    assert (d.almacen.ruta(pid) / "informe.md").exists()
    assert d.proveedores.subidor.subidas

class VideoDePago:
    def __init__(self, interno): self.interno, self.llamadas = interno, 0
    async def animar(self, imagen, prompt, destino, segundos=10.0):
        self.llamadas += 1
        await self.interno.animar(imagen, prompt, destino, segundos)
        return 0.30

async def test_pausa_por_presupuesto_y_reanuda(raiz):
    prov = proveedores_simulados()
    prov.video = VideoDePago(prov.video)
    d = _director(raiz, prov)
    d.concurrencia = 1
    pid = await d.crear("Roma", 1, "documental", 1.0)     # 1 $ → caben 3 clips de 0,30
    await d.avanzar(pid); d.aprobar_guion(pid)
    assert await d.avanzar(pid) == Fase.CLIPS
    assert "Presupuesto" in d.almacen.pausa(pid)
    assert prov.video.llamadas == 3
    d.cambiar_presupuesto(pid, 10.0)
    d.almacen.quitar_pausa(pid)
    assert await d.avanzar(pid) == Fase.APROBACION_FINAL
    assert prov.video.llamadas == 5

async def test_regenerar_imagen_invalida_clip_y_vuelve_a_montaje(raiz):
    d = _director(raiz)
    pid = await d.crear("Roma", 1, "documental", 50)
    await d.avanzar(pid); d.aprobar_guion(pid); await d.avanzar(pid)
    await d.regenerar(pid, "c01_s002", "imagen")
    e = d.almacen.cargar_guion(pid).escena("c01_s002")
    assert e.estado["imagen"] == "generado" and e.estado["clip"] == "pendiente"
    assert d.almacen.fase(pid) == Fase.CLIPS
    assert await d.avanzar(pid) == Fase.APROBACION_FINAL

async def test_errores_de_escena_pausan(raiz):
    prov = proveedores_simulados()
    interno = prov.imagen
    class Rompe:
        async def generar(self, prompt, destino):
            if destino.stem == "c01_s001": raise ValueError("rechazado")
            return await interno.generar(prompt, destino)
    prov.imagen = Rompe()
    d = _director(raiz, prov)
    pid = await d.crear("Roma", 1, "documental", 50)
    await d.avanzar(pid); d.aprobar_guion(pid)
    assert await d.avanzar(pid) == Fase.IMAGENES
    assert "c01_s001" in d.almacen.pausa(pid)
```

Nota: en `test_regenerar_imagen...`, tras regenerar en `APROBACION_FINAL` la fase debe pasar a la **primera fase con trabajo pendiente** (`CLIPS` aquí). Regla: imagen→`CLIPS`, clip→`MONTAJE`... no: clip pendiente tras regenerar clip ya se regeneró → `MONTAJE`; audio → `MONTAJE`; guion → `IMAGENES`.

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# director/director.py
import asyncio

from agentes.animador import Animador
from agentes.guionista import Guionista
from agentes.ilustrador import Ilustrador
from agentes.montador import Montador
from agentes.narrador import Narrador
from agentes.publicador import Publicador
from arquitecto.arquitecto import Arquitecto
from core.almacen import Almacen
from core.costes import estimar
from core.modelos import CLAVES, Estado, Fase
from director.contexto import Contexto, PresupuestoAgotado
from director.eventos import Bus
from proveedores.base import Proveedores

DEPENDIENTES = {"guion": list(CLAVES), "imagen": ["imagen", "clip"], "clip": ["clip"], "audio": ["audio"]}
FASE_TRAS_REGENERAR = {"guion": Fase.IMAGENES, "imagen": Fase.CLIPS, "clip": Fase.MONTAJE, "audio": Fase.MONTAJE}


class Director:
    def __init__(self, almacen: Almacen, proveedores: Proveedores, bus: Bus, concurrencia: int = 6):
        self.almacen, self.proveedores, self.bus, self.concurrencia = almacen, proveedores, bus, concurrencia
        self.arquitecto = Arquitecto()
        self.guionista, self.ilustrador, self.animador = Guionista(), Ilustrador(), Animador()
        self.narrador, self.montador, self.publicador = Narrador(), Montador(), Publicador()
        self._tareas: dict[str, asyncio.Task] = {}

    def _ctx(self, pid: str) -> Contexto:
        return Contexto(self.almacen, self.proveedores, pid, self.bus, self.concurrencia)

    def _fase(self, ctx: Contexto, fase: Fase) -> None:
        self.almacen.set_fase(ctx.pid, fase)
        ctx.emitir("director", f"fase → {fase.value}", fase=fase.value)

    async def crear(self, idea: str, duracion_min: int, tono: str, presupuesto_max: float) -> str:
        plan, coste = await self.arquitecto.planificar(self.proveedores.supervisor, idea, duracion_min, tono,
                                                       presupuesto_max)
        pid = self.almacen.crear_proyecto(plan)
        self.almacen.registrar_coste(pid, "arquitecto", "plan", coste)
        return pid

    def estimacion(self, pid: str) -> dict:
        return estimar(self.almacen.cargar_plan(pid))

    # ---------- ciclo principal
    async def avanzar(self, pid: str) -> Fase:
        ctx = self._ctx(pid)
        try:
            while not self.almacen.pausa(pid):
                fase = self.almacen.fase(pid)
                if fase in (Fase.APROBACION_GUION, Fase.APROBACION_FINAL, Fase.COMPLETADO):
                    return fase
                siguiente = await self._paso(ctx, fase)
                if siguiente is None:
                    break
                self._fase(ctx, siguiente)
        except PresupuestoAgotado as e:
            self.almacen.pausar(pid, str(e))
            ctx.emitir("arquitecto", f"⏸ {e}. Sube el presupuesto y pulsa Reanudar.")
        except Exception as e:  # noqa: BLE001
            self.almacen.pausar(pid, f"error: {e}"[:500])
            ctx.emitir("director", f"❌ {e}")
        return self.almacen.fase(pid)

    async def _paso(self, ctx: Contexto, fase: Fase) -> Fase | None:
        a = self.arquitecto
        if fase == Fase.GUION:
            if not self.almacen.tiene_guion(ctx.pid):
                await self.guionista.ejecutar(ctx)
            for eid, motivo in await a.revisar_guion(ctx):
                a.marcar_regeneracion(ctx, [eid])
                await self.guionista.regenerar_escena(ctx, eid, motivo)
                ctx.emitir("arquitecto", f"reescrita {eid}: {motivo}")
            return Fase.APROBACION_GUION
        if fase == Fase.IMAGENES:
            return await self._produccion(ctx, self.ilustrador, a.revisar_imagenes, Fase.CLIPS)
        if fase == Fase.CLIPS:
            return await self._produccion(ctx, self.animador, a.revisar_clips, Fase.AUDIO)
        if fase == Fase.AUDIO:
            return await self._produccion(ctx, self.narrador, None, Fase.MONTAJE)
        if fase == Fase.MONTAJE:
            r = await self.montador.ejecutar(ctx)
            if not r.ok:
                self.almacen.pausar(ctx.pid, "; ".join(r.errores))
                return None
            await self.publicador.preparar(ctx)
            return Fase.APROBACION_FINAL
        if fase == Fase.PUBLICACION:
            r = await self.publicador.subir(ctx)
            if not r.ok:
                self.almacen.pausar(ctx.pid, "; ".join(r.errores))
                return None
            a.informe(ctx)
            return Fase.COMPLETADO
        raise ValueError(f"fase sin paso: {fase}")

    async def _produccion(self, ctx, agente, revisar, siguiente: Fase) -> Fase | None:
        r = await agente.ejecutar(ctx)
        if revisar and r.ok:
            malas = await revisar(ctx)
            if malas:
                ids = [i for i, _ in malas]
                self.arquitecto.marcar_regeneracion(ctx, ids)
                ctx.emitir("arquitecto", f"regenerar {len(ids)}: " + "; ".join(f"{i} ({m})" for i, m in malas))
                r = await agente.ejecutar(ctx, solo=ids)
        if not r.ok:
            self.almacen.pausar(ctx.pid, f"{agente.nombre}: {len(r.errores)} escenas con error — "
                                         + "; ".join(r.errores[:5]))
            return None
        return siguiente

    # ---------- control
    def ocupado(self, pid: str) -> bool:
        t = self._tareas.get(pid)
        return bool(t and not t.done())

    def lanzar(self, pid: str) -> None:
        if not self.ocupado(pid):
            self._tareas[pid] = asyncio.create_task(self.avanzar(pid))

    def _exigir(self, pid: str, fase: Fase) -> None:
        if self.almacen.fase(pid) != fase:
            raise ValueError(f"el proyecto está en {self.almacen.fase(pid).value}, no en {fase.value}")

    def aprobar_guion(self, pid: str) -> None:
        self._exigir(pid, Fase.APROBACION_GUION)
        self._fase(self._ctx(pid), Fase.IMAGENES)

    def aprobar_final(self, pid: str, titulo: str, miniatura: str, privacidad: str = "private",
                      publicar_en: str | None = None) -> None:
        self._exigir(pid, Fase.APROBACION_FINAL)
        d = self.almacen.cargar_json(pid, "publicacion.json")
        d.update(titulo_elegido=titulo, miniatura_elegida=miniatura, privacidad=privacidad, publicar_en=publicar_en)
        self.almacen.guardar_json(pid, "publicacion.json", d)
        self._fase(self._ctx(pid), Fase.PUBLICACION)

    def reanudar(self, pid: str) -> None:
        self.almacen.quitar_pausa(pid)
        self.lanzar(pid)

    def cambiar_presupuesto(self, pid: str, usd: float) -> None:
        plan = self.almacen.cargar_plan(pid)
        plan.presupuesto_max = float(usd)
        self.almacen.guardar_plan(pid, plan)

    async def regenerar(self, pid: str, escena_id: str, clave: str) -> None:
        if self.ocupado(pid):
            raise ValueError("el proyecto está trabajando; espera a que termine")
        ctx = self._ctx(pid)
        g = self.almacen.cargar_guion(pid)
        e = g.escena(escena_id)
        for k in DEPENDIENTES[clave]:
            e.estado[k] = Estado.PENDIENTE
        self.almacen.guardar_guion(pid, g)
        try:
            if clave == "guion":
                await self.guionista.regenerar_escena(ctx, escena_id, "petición del usuario")
            else:
                agente = {"imagen": self.ilustrador, "clip": self.animador, "audio": self.narrador}[clave]
                await agente.ejecutar(ctx, solo=[escena_id])
        except PresupuestoAgotado as ex:
            self.almacen.pausar(pid, str(ex))
        fase = self.almacen.fase(pid)
        if fase in (Fase.APROBACION_FINAL, Fase.MONTAJE) or (
                fase not in (Fase.GUION, Fase.APROBACION_GUION) and
                list(Fase).index(fase) > list(Fase).index(FASE_TRAS_REGENERAR[clave])):
            self._fase(ctx, FASE_TRAS_REGENERAR[clave])

    async def regenerar_capitulo(self, pid: str, numero: int) -> None:
        self._exigir(pid, Fase.APROBACION_GUION)
        await self.guionista.regenerar_capitulo(self._ctx(pid), numero)
```

- [ ] **Step 4: Run** `pytest tests/test_director.py -v` → PASS
- [ ] **Step 5: Run toda la suite** `pytest -v` → PASS
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: director máquina de estados"`

---

### Task 13: Proveedores reales y fábrica

**Files:**
- Create: `proveedores/anthropic_llm.py`, `proveedores/fal.py`, `proveedores/tts.py`, `proveedores/youtube.py`, `proveedores/fabrica.py`, `tests/test_proveedores_reales.py`

**Interfaces:**
- Consumes: `Ajustes`, `ErrorTransitorio`, `ErrorPermanente`, protocolos de `proveedores.base`.
- Produces: `AnthropicLLM(clave, modelo, precio_in, precio_out)`, `FalImagen(endpoint, precio)`, `FalVideo(endpoint, precio)`, `ElevenLabsTTS(clave, voz, precio_por_1k_car, cliente=None)`, `OpenAITTS(clave, voz, precio_por_1k_car, cliente=None)`, `SubidorYouTube(client_secret: Path, token: Path)` + `conectar_youtube(client_secret, token) -> None` (abre navegador, lo ejecuta el usuario), `construir(ajustes: Ajustes) -> Proveedores`.

- [ ] **Step 1: Confirmar IDs y precios actuales** — cargar la skill `claude-api` y confirmar IDs de modelo y precio por millón de tokens de `claude-sonnet-5-5` / `claude-opus-5-5`; consultar en fal.ai los endpoints de Flux e image-to-video (Kling) y sus esquemas de entrada/salida y precio; consultar precio de ElevenLabs/OpenAI TTS. Actualizar `.env.example` y `core/costes.py::PRECIOS` con los valores confirmados. Commit: `chore: precios y endpoints verificados`.

- [ ] **Step 2: Tests (fallan)**

```python
# tests/test_proveedores_reales.py
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
```

- [ ] **Step 3: Run** → FAIL
- [ ] **Step 4: Implementar**

```python
# proveedores/anthropic_llm.py
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
```

```python
# proveedores/fal.py
from pathlib import Path

import fal_client
import httpx

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio


async def descargar(url: str, destino: Path) -> None:
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.get(url)
        r.raise_for_status()
        destino.write_bytes(r.content)


async def _llamar(endpoint: str, argumentos: dict) -> dict:
    try:
        return await fal_client.subscribe_async(endpoint, arguments=argumentos)
    except httpx.TransportError as e:
        raise ErrorTransitorio(str(e)) from e
    except Exception as e:  # fal_client lanza errores HTTP propios
        texto = str(e)
        if any(c in texto for c in ("429", "500", "502", "503", "504", "timeout")):
            raise ErrorTransitorio(texto) from e
        raise ErrorPermanente(texto) from e


class FalImagen:
    def __init__(self, endpoint: str, precio: float):
        self.endpoint, self.precio = endpoint, precio

    async def generar(self, prompt: str, destino: Path) -> float:
        r = await _llamar(self.endpoint, {"prompt": prompt, "image_size": {"width": 1920, "height": 1080},
                                          "num_images": 1})
        await descargar(r["images"][0]["url"], destino)
        return self.precio


class FalVideo:
    def __init__(self, endpoint: str, precio: float):
        self.endpoint, self.precio = endpoint, precio

    async def animar(self, imagen: Path, prompt: str, destino: Path, segundos: float = 10.0) -> float:
        url = await fal_client.upload_file_async(imagen)
        r = await _llamar(self.endpoint, {"prompt": prompt, "image_url": url, "duration": str(int(segundos))})
        await descargar(r["video"]["url"], destino)
        return self.precio
```

```python
# proveedores/tts.py
from pathlib import Path

import httpx

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio


async def _post(cliente: httpx.AsyncClient, url: str, headers: dict, cuerpo: dict) -> bytes:
    try:
        r = await cliente.post(url, headers=headers, json=cuerpo, timeout=120)
    except httpx.TransportError as e:
        raise ErrorTransitorio(str(e)) from e
    if r.status_code == 429 or r.status_code >= 500:
        raise ErrorTransitorio(f"{r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        raise ErrorPermanente(f"{r.status_code}: {r.text[:200]}")
    return r.content


class ElevenLabsTTS:
    def __init__(self, clave: str, voz: str, precio_por_1k_car: float, cliente: httpx.AsyncClient | None = None,
                 modelo: str = "eleven_multilingual_v2"):
        self.clave, self.voz, self.precio, self.modelo = clave, voz, precio_por_1k_car, modelo
        self.cliente = cliente or httpx.AsyncClient()

    async def sintetizar(self, texto: str, destino: Path) -> float:
        audio = await _post(self.cliente, f"https://api.elevenlabs.io/v1/text-to-speech/{self.voz}",
                            {"xi-api-key": self.clave, "accept": "audio/mpeg"},
                            {"text": texto, "model_id": self.modelo})
        destino.write_bytes(audio)
        return len(texto) / 1000 * self.precio


class OpenAITTS:
    def __init__(self, clave: str, voz: str, precio_por_1k_car: float, cliente: httpx.AsyncClient | None = None,
                 modelo: str = "gpt-4o-mini-tts"):
        self.clave, self.voz, self.precio, self.modelo = clave, voz, precio_por_1k_car, modelo
        self.cliente = cliente or httpx.AsyncClient()

    async def sintetizar(self, texto: str, destino: Path) -> float:
        audio = await _post(self.cliente, "https://api.openai.com/v1/audio/speech",
                            {"Authorization": f"Bearer {self.clave}"},
                            {"model": self.modelo, "voice": self.voz, "input": texto, "response_format": "mp3"})
        destino.write_bytes(audio)
        return len(texto) / 1000 * self.precio
```

```python
# proveedores/youtube.py
import asyncio
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from herramientas.reintentos import ErrorPermanente, ErrorTransitorio

ALCANCES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]


def conectar_youtube(client_secret: Path, token: Path) -> None:
    """Abre el navegador para que el usuario autorice su canal. Guarda el token en local."""
    flujo = InstalledAppFlow.from_client_secrets_file(str(client_secret), ALCANCES)
    cred = flujo.run_local_server(port=0)
    token.write_text(cred.to_json(), encoding="utf-8")


def youtube_conectado(token: Path) -> bool:
    return token.exists()


class SubidorYouTube:
    def __init__(self, client_secret: Path, token: Path):
        self.client_secret, self.token = client_secret, token

    def _servicio(self):
        if not self.token.exists():
            raise ErrorPermanente("YouTube no conectado: ve a Ajustes → Conectar YouTube")
        cred = Credentials.from_authorized_user_file(str(self.token), ALCANCES)
        if cred.expired and cred.refresh_token:
            cred.refresh(Request())
            self.token.write_text(cred.to_json(), encoding="utf-8")
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
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(miniatura))).execute()
            if srt and srt.exists():
                yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "es",
                                                                       "name": "Español"}},
                                     media_body=MediaFileUpload(str(srt))).execute()
            return vid
        except HttpError as e:
            if e.resp.status in (429, 500, 503):
                raise ErrorTransitorio(str(e)) from e
            raise ErrorPermanente(str(e)) from e

    async def subir(self, video: Path, meta: dict, miniatura: Path, srt: Path | None) -> str:
        return await asyncio.to_thread(self._subir, video, meta, miniatura, srt)
```

```python
# proveedores/fabrica.py
from pathlib import Path

from core.config import Ajustes
from core.costes import PRECIOS
from proveedores.base import Proveedores
from proveedores.simulados import proveedores_simulados

# USD por millón de tokens (entrada, salida). Confirmados en Task 13 Step 1.
PRECIOS_LLM = {"claude-sonnet-5-5": (3.0, 15.0), "claude-opus-5-5": (5.0, 25.0)}
PRECIO_TTS_1K = {"elevenlabs": 0.30, "openai": 0.015}
TOKEN_YOUTUBE = Path("token_youtube.json")


def construir(a: Ajustes) -> Proveedores:
    if a.modo == "simulado":
        return proveedores_simulados()
    faltan = [n for n, v in [("ANTHROPIC_API_KEY", a.anthropic_key), ("FAL_KEY", a.fal_key)] if not v]
    if a.tts == "elevenlabs" and not (a.elevenlabs_key and a.elevenlabs_voz):
        faltan.append("ELEVENLABS_API_KEY/DV_ELEVENLABS_VOZ")
    if a.tts == "openai" and not a.openai_key:
        faltan.append("OPENAI_API_KEY")
    if faltan:
        raise ValueError("Faltan claves en .env: " + ", ".join(faltan))

    import os
    os.environ["FAL_KEY"] = a.fal_key
    from proveedores.anthropic_llm import AnthropicLLM
    from proveedores.fal import FalImagen, FalVideo
    from proveedores.tts import ElevenLabsTTS, OpenAITTS
    from proveedores.youtube import SubidorYouTube

    tts = (ElevenLabsTTS(a.elevenlabs_key, a.elevenlabs_voz, PRECIO_TTS_1K["elevenlabs"]) if a.tts == "elevenlabs"
           else OpenAITTS(a.openai_key, a.openai_voz, PRECIO_TTS_1K["openai"]))
    return Proveedores(
        llm=AnthropicLLM(a.anthropic_key, a.modelo_guion, *PRECIOS_LLM.get(a.modelo_guion, (3.0, 15.0))),
        supervisor=AnthropicLLM(a.anthropic_key, a.modelo_supervisor, *PRECIOS_LLM.get(a.modelo_supervisor, (5.0, 25.0))),
        imagen=FalImagen(a.fal_imagen, PRECIOS["imagen"]),
        video=_VideoPorPlan(FalVideo(a.fal_video_barato, PRECIOS["clip"]["barato"]),
                            FalVideo(a.fal_video_premium, PRECIOS["clip"]["premium"])),
        tts=tts,
        subidor=SubidorYouTube(a.youtube_client_secret, TOKEN_YOUTUBE),
    )


class _VideoPorPlan:
    """Elige barato/premium; el Director fija `modelo` antes de cada fase CLIPS."""
    def __init__(self, barato, premium):
        self.barato, self.premium, self.modelo = barato, premium, "barato"

    async def animar(self, imagen, prompt, destino, segundos=10.0):
        return await (self.premium if self.modelo == "premium" else self.barato).animar(imagen, prompt, destino, segundos)
```

Y en `director/director.py::_paso`, rama `Fase.CLIPS`, antes de producir:
```python
            if hasattr(self.proveedores.video, "modelo"):
                self.proveedores.video.modelo = ctx.plan.modelo_video
```

- [ ] **Step 5: Run** `pytest -v` → PASS
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: proveedores reales y fábrica"`

---

### Task 14: API JSON y eventos en vivo

**Files:**
- Create: `app/__init__.py`, `app/main.py`, `app/api.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `Director`, `Almacen`, `Bus`, `construir`, `Ajustes`.
- Produces: `crear_app(ajustes: Ajustes | None = None, proveedores: Proveedores | None = None) -> FastAPI` con `app.state.director`. Rutas bajo `/api`:
  - `GET /api/proyectos` → lista; `POST /api/proyectos` `{idea, duracion_min, tono, presupuesto_max}` → `{id}` y lanza.
  - `GET /api/proyectos/{pid}` → `{plan, fase, pausa, coste, costes, estimacion, guion|null, montaje|null, publicacion|null, ocupado}`.
  - `POST /api/proyectos/{pid}/aprobar-guion`, `POST .../aprobar-final` `{titulo, miniatura, privacidad, publicar_en}`, `POST .../reanudar`, `POST .../presupuesto` `{usd}`, `POST .../escenas/{eid}` `{narracion?, imagen_prompt?, movimiento_prompt?}` (solo en ⏸1/⏸2; resetea dependientes como "guion"/"imagen"), `POST .../escenas/{eid}/regenerar/{clave}`, `POST .../capitulos/{n}/regenerar`.
  - `GET /api/proyectos/{pid}/eventos` (SSE).
  - `GET /media/{pid}/{ruta}` sirve archivos del proyecto (bloquea `..`).
  - Errores `ValueError` → 409 con `{"detail"}`; `KeyError` → 404.

- [ ] **Step 1: Test (falla)**

```python
# tests/test_api.py
import asyncio
import httpx
import pytest
from app.main import crear_app
from core.config import Ajustes

@pytest.fixture
async def cliente(raiz):
    app = crear_app(Ajustes(modo="simulado", raiz=raiz))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c

async def _esperar(c, pid, fase):
    for _ in range(600):
        d = (await c.get(f"/api/proyectos/{pid}")).json()
        if d["fase"] == fase and not d["ocupado"]:
            return d
        await asyncio.sleep(0.1)
    raise AssertionError(d)

async def test_flujo_por_api(cliente):
    r = await cliente.post("/api/proyectos", json={"idea": "Roma", "duracion_min": 1, "tono": "documental",
                                                   "presupuesto_max": 50})
    pid = r.json()["id"]
    d = await _esperar(cliente, pid, "aprobacion_guion")
    assert len(d["guion"]["escenas"]) == 5 and d["estimacion"]["total"] >= 0
    eid = d["guion"]["escenas"][0]["id"]
    r = await cliente.post(f"/api/proyectos/{pid}/escenas/{eid}", json={"narracion": "texto editado " * 5})
    assert r.status_code == 200
    assert (await cliente.post(f"/api/proyectos/{pid}/aprobar-final", json={"titulo": "x", "miniatura": "y"})).status_code == 409
    await cliente.post(f"/api/proyectos/{pid}/aprobar-guion")
    d = await _esperar(cliente, pid, "aprobacion_final")
    m = await cliente.get(f"/media/{pid}/final.mp4")
    assert m.status_code == 200
    assert (await cliente.get(f"/media/{pid}/../director.db")).status_code in (400, 404)
    pub = d["publicacion"]
    await cliente.post(f"/api/proyectos/{pid}/aprobar-final",
                       json={"titulo": pub["titulos"][0], "miniatura": pub["miniaturas"][0]})
    await _esperar(cliente, pid, "completado")

async def test_404(cliente):
    assert (await cliente.get("/api/proyectos/nope")).status_code == 404
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar**

```python
# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.almacen import Almacen
from core.config import Ajustes
from director.director import Director
from director.eventos import Bus
from proveedores.base import Proveedores
from proveedores.fabrica import construir


def crear_app(ajustes: Ajustes | None = None, proveedores: Proveedores | None = None) -> FastAPI:
    ajustes = ajustes or Ajustes.desde_entorno()
    app = FastAPI(title="DirectorVideos")
    app.state.ajustes = ajustes
    app.state.director = Director(Almacen(ajustes.raiz), proveedores or construir(ajustes), Bus(),
                                  ajustes.concurrencia)

    @app.exception_handler(ValueError)
    async def _conflicto(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(KeyError)
    async def _no_existe(_: Request, e: KeyError):
        return JSONResponse({"detail": f"no existe: {e}"}, status_code=404)

    from app.api import router as api
    from app.web import router as web
    app.include_router(api)
    app.include_router(web)
    return app
```

```python
# app/api.py
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.modelos import Estado, Fase

router = APIRouter()
EDITABLES = {Fase.APROBACION_GUION, Fase.APROBACION_FINAL}


class NuevoProyecto(BaseModel):
    idea: str = Field(min_length=3)
    duracion_min: int = Field(ge=1, le=50)
    tono: str = "documental"
    presupuesto_max: float = Field(gt=0, default=50.0)


class Aprobacion(BaseModel):
    titulo: str
    miniatura: str
    privacidad: str = "private"
    publicar_en: str | None = None


class EdicionEscena(BaseModel):
    narracion: str | None = None
    imagen_prompt: str | None = None
    movimiento_prompt: str | None = None


def _d(req: Request):
    return req.app.state.director


def detalle(director, pid: str) -> dict:
    a = director.almacen
    fase = a.fase(pid)
    return {"id": pid, "plan": a.cargar_plan(pid).model_dump(), "fase": fase.value, "pausa": a.pausa(pid),
            "coste": round(a.coste_total(pid), 2), "costes": a.costes_por_agente(pid),
            "estimacion": director.estimacion(pid),
            "guion": a.cargar_guion(pid).model_dump() if a.tiene_guion(pid) else None,
            "montaje": a.cargar_json(pid, "montaje.json"), "publicacion": a.cargar_json(pid, "publicacion.json"),
            "ocupado": director.ocupado(pid), "logs": a.logs(pid, 50)}


@router.get("/api/proyectos")
async def listar(req: Request):
    return _d(req).almacen.listar()


@router.post("/api/proyectos")
async def crear(req: Request, datos: NuevoProyecto):
    d = _d(req)
    pid = await d.crear(datos.idea, datos.duracion_min, datos.tono, datos.presupuesto_max)
    d.lanzar(pid)
    return {"id": pid}


@router.get("/api/proyectos/{pid}")
async def ver(req: Request, pid: str):
    return detalle(_d(req), pid)


@router.post("/api/proyectos/{pid}/aprobar-guion")
async def aprobar_guion(req: Request, pid: str):
    d = _d(req); d.aprobar_guion(pid); d.lanzar(pid)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/aprobar-final")
async def aprobar_final(req: Request, pid: str, datos: Aprobacion):
    d = _d(req); d.aprobar_final(pid, datos.titulo, datos.miniatura, datos.privacidad, datos.publicar_en)
    d.lanzar(pid)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/reanudar")
async def reanudar(req: Request, pid: str):
    _d(req).reanudar(pid)
    return {"ok": True}


@router.post("/api/proyectos/{pid}/presupuesto")
async def presupuesto(req: Request, pid: str, datos: dict):
    _d(req).cambiar_presupuesto(pid, float(datos["usd"]))
    return {"ok": True}


@router.post("/api/proyectos/{pid}/escenas/{eid}")
async def editar_escena(req: Request, pid: str, eid: str, datos: EdicionEscena):
    d = _d(req)
    if d.almacen.fase(pid) not in EDITABLES or d.ocupado(pid):
        raise ValueError("solo se puede editar en los puntos de aprobación")
    g = d.almacen.cargar_guion(pid)
    e = g.escena(eid)
    if datos.narracion is not None:
        e.narracion, e.estado["audio"] = datos.narracion, Estado.PENDIENTE
    if datos.imagen_prompt is not None:
        e.imagen_prompt = datos.imagen_prompt
        e.estado["imagen"] = e.estado["clip"] = Estado.PENDIENTE
    if datos.movimiento_prompt is not None:
        e.movimiento_prompt, e.estado["clip"] = datos.movimiento_prompt, Estado.PENDIENTE
    d.almacen.guardar_guion(pid, g)
    if d.almacen.fase(pid) == Fase.APROBACION_FINAL:
        d.almacen.set_fase(pid, Fase.IMAGENES)      # el Director salta lo ya generado
    return e.model_dump()


@router.post("/api/proyectos/{pid}/escenas/{eid}/regenerar/{clave}")
async def regenerar(req: Request, pid: str, eid: str, clave: str):
    if clave not in ("guion", "imagen", "clip", "audio"):
        raise HTTPException(400, "clave inválida")
    await _d(req).regenerar(pid, eid, clave)
    return _d(req).almacen.cargar_guion(pid).escena(eid).model_dump()


@router.post("/api/proyectos/{pid}/capitulos/{numero}/regenerar")
async def regenerar_capitulo(req: Request, pid: str, numero: int):
    await _d(req).regenerar_capitulo(pid, numero)
    return {"ok": True}


@router.get("/api/proyectos/{pid}/eventos")
async def eventos(req: Request, pid: str):
    bus = _d(req).bus
    cola = bus.suscribir(pid)

    async def flujo():
        try:
            while not await req.is_disconnected():
                try:
                    ev = await asyncio.wait_for(cola.get(), timeout=15)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.desuscribir(pid, cola)
    return StreamingResponse(flujo(), media_type="text/event-stream")


@router.get("/media/{pid}/{ruta:path}")
async def media(req: Request, pid: str, ruta: str):
    base = _d(req).almacen.ruta(pid).resolve()
    destino = (base / ruta).resolve()
    if base not in destino.parents or not destino.is_file():
        raise HTTPException(404)
    return FileResponse(destino)
```

Crear `app/web.py` provisional para que importe:
```python
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 4: Run** `pytest tests/test_api.py -v` → PASS
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: API JSON y eventos SSE"`

---

### Task 15: Interfaz web (htmx)

**Files:**
- Modify: `app/web.py`
- Create: `app/templates/base.html`, `panel.html`, `proyecto.html`, `_timeline.html`, `_escenas.html`, `_revision.html`, `ajustes.html`, `run.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: `app.api.detalle`, `Director`, `conectar_youtube`, `youtube_conectado`, `TOKEN_YOUTUBE`.
- Produces: páginas `GET /` (panel + formulario nueva idea + coste del mes), `POST /proyectos` (form → redirige a `/proyectos/{id}`), `GET /proyectos/{pid}` (línea de tiempo de agentes, pausa con botón Reanudar y campo presupuesto, estimación, editor de guion en ⏸1, galería imagen/clip por escena con botones regenerar, revisión final en ⏸2 con reproductor, títulos, miniaturas, privacidad y fecha), `GET /proyectos/{pid}/parcial` (fragmento que htmx refresca al recibir SSE), `GET /ajustes`, `POST /ajustes/youtube` (lanza el OAuth en un hilo).

- [ ] **Step 1: Test (falla)**

```python
# tests/test_web.py
import asyncio
import httpx
from app.main import crear_app
from core.config import Ajustes
from tests.test_api import _esperar

async def test_paginas(raiz):
    app = crear_app(Ajustes(modo="simulado", raiz=raiz))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/")
        assert r.status_code == 200 and "Nueva idea" in r.text
        r = await c.post("/proyectos", data={"idea": "Roma antigua", "duracion_min": "1", "tono": "documental",
                                             "presupuesto_max": "20"}, follow_redirects=False)
        assert r.status_code == 303
        pid = r.headers["location"].rsplit("/", 1)[-1]
        await _esperar(c, pid, "aprobacion_guion")
        r = await c.get(f"/proyectos/{pid}")
        for texto in ("Guionista", "Ilustrador", "Animador", "Narrador", "Montador", "Publicador",
                      "Aprobar guion", "c01_s001"):
            assert texto in r.text
        assert (await c.get("/ajustes")).status_code == 200
```

- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implementar `app/web.py`**

```python
# app/web.py
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api import detalle
from core.costes import PRECIOS

router = APIRouter()
plantillas = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
AGENTES = [("guionista", "Guionista", ["guion"]), ("ilustrador", "Ilustrador", ["imagenes"]),
           ("animador", "Animador", ["clips"]), ("narrador", "Narrador", ["audio"]),
           ("montador", "Montador", ["montaje"]), ("publicador", "Publicador", ["publicacion"])]
ORDEN = ["guion", "aprobacion_guion", "imagenes", "clips", "audio", "montaje", "aprobacion_final",
         "publicacion", "completado"]


def estado_agente(fase: str, pausa: str | None, fases_agente: list[str]) -> str:
    i_fase, i_ag = ORDEN.index(fase), ORDEN.index(fases_agente[0])
    if i_fase > i_ag:
        return "hecho"
    if i_fase == i_ag:
        return "error" if pausa else "trabajando"
    if fase in ("aprobacion_guion", "aprobacion_final") and ORDEN.index(fase) + 1 == i_ag:
        return "esperando"
    return "cola"


def _ctx(req: Request, pid: str) -> dict:
    d = req.app.state.director
    det = detalle(d, pid)
    det["agentes"] = [(clave, nombre, estado_agente(det["fase"], det["pausa"], fases))
                      for clave, nombre, fases in AGENTES]
    return {"request": req, "p": det}


@router.get("/", response_class=HTMLResponse)
async def panel(req: Request):
    a = req.app.state.director.almacen
    hoy = datetime.now()
    return plantillas.TemplateResponse(req, "panel.html", {
        "proyectos": a.listar(), "coste_mes": a.coste_mes(hoy.year, hoy.month),
        "modo": req.app.state.ajustes.modo})


@router.post("/proyectos")
async def crear(req: Request, idea: str = Form(...), duracion_min: int = Form(...), tono: str = Form("documental"),
                presupuesto_max: float = Form(50.0)):
    d = req.app.state.director
    pid = await d.crear(idea, duracion_min, tono, presupuesto_max)
    d.lanzar(pid)
    return RedirectResponse(f"/proyectos/{pid}", status_code=303)


@router.get("/proyectos/{pid}", response_class=HTMLResponse)
async def proyecto(req: Request, pid: str):
    return plantillas.TemplateResponse(req, "proyecto.html", _ctx(req, pid))


@router.get("/proyectos/{pid}/parcial", response_class=HTMLResponse)
async def parcial(req: Request, pid: str):
    return plantillas.TemplateResponse(req, "_timeline.html", _ctx(req, pid))


@router.get("/ajustes", response_class=HTMLResponse)
async def ajustes(req: Request):
    from proveedores.fabrica import TOKEN_YOUTUBE
    from proveedores.youtube import youtube_conectado
    aj = req.app.state.ajustes
    return plantillas.TemplateResponse(req, "ajustes.html", {
        "aj": aj, "precios": PRECIOS, "youtube": youtube_conectado(TOKEN_YOUTUBE),
        "claves": {"Anthropic": bool(aj.anthropic_key), "fal.ai": bool(aj.fal_key),
                   "ElevenLabs": bool(aj.elevenlabs_key), "OpenAI": bool(aj.openai_key)}})


@router.post("/ajustes/youtube")
async def conectar(req: Request):
    from proveedores.fabrica import TOKEN_YOUTUBE
    from proveedores.youtube import conectar_youtube
    asyncio.create_task(asyncio.to_thread(conectar_youtube, req.app.state.ajustes.youtube_client_secret,
                                          TOKEN_YOUTUBE))
    return RedirectResponse("/ajustes", status_code=303)
```

- [ ] **Step 4: Plantillas**

`app/templates/base.html`:
```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DirectorVideos</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js"></script>
  <style>
    :root { --bg:#0f1115; --panel:#181b22; --texto:#e6e6e6; --tenue:#8a8f98; --acento:#e5484d; --ok:#30a46c; --aviso:#f5a524; }
    * { box-sizing:border-box } body { margin:0; font:15px/1.5 system-ui, sans-serif; background:var(--bg); color:var(--texto) }
    header { padding:12px 24px; background:var(--panel); display:flex; gap:24px; align-items:center }
    header a { color:var(--texto); text-decoration:none } main { padding:24px; max-width:1300px; margin:auto }
    .tarjeta { background:var(--panel); border-radius:10px; padding:16px; margin-bottom:16px }
    button, .boton { background:var(--acento); color:#fff; border:0; border-radius:6px; padding:8px 14px; cursor:pointer }
    button.sec { background:#2a2f3a } input, textarea, select { width:100%; background:#0f1115; color:var(--texto);
      border:1px solid #2a2f3a; border-radius:6px; padding:8px } textarea { min-height:70px }
    .timeline { display:flex; gap:8px; flex-wrap:wrap } .paso { flex:1; min-width:140px; padding:10px; border-radius:8px; background:#11141a; text-align:center }
    .hecho{border-bottom:3px solid var(--ok)} .trabajando{border-bottom:3px solid var(--aviso)} .error{border-bottom:3px solid var(--acento)} .esperando{border-bottom:3px solid #6e56cf}
    .rejilla { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:12px }
    .escena img, .escena video { width:100%; border-radius:6px; aspect-ratio:16/9; object-fit:cover; background:#000 }
    .tenue { color:var(--tenue); font-size:13px } table { width:100%; border-collapse:collapse } td,th { padding:6px; text-align:left; border-bottom:1px solid #2a2f3a }
  </style>
</head>
<body>
  <header><strong>🎬 DirectorVideos</strong><a href="/">Panel</a><a href="/ajustes">Ajustes</a></header>
  <main>{% block contenido %}{% endblock %}</main>
</body>
</html>
```

`app/templates/panel.html`:
```html
{% extends "base.html" %}
{% block contenido %}
<div class="tarjeta">
  <h2>Nueva idea</h2>
  {% if modo == "simulado" %}<p class="tenue">Modo simulado: no se gasta dinero.</p>{% endif %}
  <form method="post" action="/proyectos" style="display:grid;gap:10px;grid-template-columns:3fr 1fr 1fr 1fr auto;align-items:end">
    <label>Idea<input name="idea" required minlength="3" placeholder="La caída del Imperio romano"></label>
    <label>Minutos<input name="duracion_min" type="number" min="1" max="50" value="10"></label>
    <label>Tono<input name="tono" value="documental"></label>
    <label>Presupuesto $<input name="presupuesto_max" type="number" step="0.5" value="50"></label>
    <button>Crear</button>
  </form>
</div>
<div class="tarjeta">
  <h2>Proyectos <span class="tenue">· gasto del mes {{ "%.2f"|format(coste_mes) }} $</span></h2>
  <table><tr><th>Título / idea</th><th>Fase</th><th>Coste</th><th>Creado</th></tr>
  {% for p in proyectos %}
    <tr><td><a href="/proyectos/{{ p.id }}" style="color:inherit">{{ p.titulo or p.idea }}</a>{% if p.pausa %} ⏸{% endif %}</td>
        <td>{{ p.fase }}</td><td>{{ "%.2f"|format(p.coste) }} $</td><td class="tenue">{{ p.creado[:16] }}</td></tr>
  {% else %}<tr><td colspan="4" class="tenue">Aún no hay proyectos.</td></tr>{% endfor %}
  </table>
</div>
{% endblock %}
```

`app/templates/proyecto.html`:
```html
{% extends "base.html" %}
{% block contenido %}
<div hx-ext="sse" sse-connect="/api/proyectos/{{ p.id }}/eventos">
  <div id="vivo" hx-get="/proyectos/{{ p.id }}/parcial" hx-trigger="sse:message throttle:2s" hx-swap="innerHTML">
    {% include "_timeline.html" %}
  </div>
</div>
{% if p.fase == "aprobacion_guion" %}
  <div class="tarjeta">
    <h2>⏸ Revisión del guion: {{ p.guion.titulo }}</h2>
    <p><b>Gancho:</b> {{ p.guion.gancho }}</p>
    <p class="tenue"><b>Biblia visual:</b> {{ p.guion.biblia_visual }} · <b>Ángulo:</b> {{ p.plan.angulo }} ·
      <b>Modelo de vídeo:</b> {{ p.plan.modelo_video }}</p>
    <p><b>Coste estimado:</b> {{ p.estimacion.total }} $ (clips {{ p.estimacion.clips }} $, imágenes {{ p.estimacion.imagenes }} $)
      · tope {{ p.plan.presupuesto_max }} $</p>
    <button hx-post="/api/proyectos/{{ p.id }}/aprobar-guion" hx-on::after-request="location.reload()">✅ Aprobar guion</button>
  </div>
{% endif %}
{% if p.fase == "aprobacion_final" %}{% include "_revision.html" %}{% endif %}
{% if p.guion %}{% include "_escenas.html" %}{% endif %}
{% endblock %}
```

`app/templates/_timeline.html`:
```html
<div class="tarjeta">
  <h2>{{ p.guion.titulo if p.guion else p.plan.idea }}</h2>
  <div class="timeline">
    <div class="paso hecho">🧠 Arquitecto<br><span class="tenue">{{ p.plan.duracion_min }} min · {{ p.plan.tono }}</span></div>
    {% for clave, nombre, estado in p.agentes %}
      <div class="paso {{ estado }}">{{ loop.index }}. {{ nombre }}<br>
        <span class="tenue">{{ {"hecho":"✅ hecho","trabajando":"⚙️ trabajando","error":"❌ parado","esperando":"⏸ esperando","cola":"⏳ en cola"}[estado] }}
        {% if p.costes.get(clave) %} · {{ "%.2f"|format(p.costes[clave]) }} ${% endif %}</span></div>
    {% endfor %}
  </div>
  <p>Fase: <b>{{ p.fase }}</b> · Gastado: <b>{{ p.coste }} $</b> de {{ p.plan.presupuesto_max }} $
    {% if p.ocupado %} · <span class="tenue">trabajando…</span>{% endif %}</p>
  {% if p.pausa %}
    <div style="border-left:3px solid var(--acento);padding-left:12px">
      <p>⏸ <b>Pausado:</b> {{ p.pausa }}</p>
      <form hx-post="/api/proyectos/{{ p.id }}/presupuesto" hx-ext="json-enc" style="display:flex;gap:8px;max-width:420px">
        <input name="usd" type="number" step="0.5" value="{{ p.plan.presupuesto_max }}"><button class="sec">Cambiar tope</button>
      </form><br>
      <button hx-post="/api/proyectos/{{ p.id }}/reanudar">▶ Reanudar</button>
    </div>
  {% endif %}
  <details><summary class="tenue">Registro</summary>
    {% for l in p.logs %}<div class="tenue">{{ l.ts[11:19] }} · {{ l.agente }} · {{ l.mensaje }}</div>{% endfor %}
  </details>
</div>
```

`app/templates/_escenas.html`:
```html
{% set editable = p.fase in ("aprobacion_guion", "aprobacion_final") and not p.ocupado %}
{% for cap in p.guion.capitulos %}
<div class="tarjeta">
  <h3>Capítulo {{ cap.numero }}: {{ cap.titulo }}
    {% if p.fase == "aprobacion_guion" %}<button class="sec" hx-post="/api/proyectos/{{ p.id }}/capitulos/{{ cap.numero }}/regenerar"
      hx-on::after-request="location.reload()">↻ Reescribir capítulo</button>{% endif %}</h3>
  <div class="rejilla">
  {% for e in p.guion.escenas if e.capitulo == cap.numero %}
    <div class="escena">
      <b>{{ e.id }}</b> <span class="tenue">img {{ e.estado.imagen }} · clip {{ e.estado.clip }} · audio {{ e.estado.audio }}</span>
      {% if e.estado.clip == "generado" %}<video src="/media/{{ p.id }}/clips/{{ e.id }}.mp4" controls preload="none"
        poster="/media/{{ p.id }}/imagenes/{{ e.id }}.png"></video>
      {% elif e.estado.imagen == "generado" %}<img src="/media/{{ p.id }}/imagenes/{{ e.id }}.png" loading="lazy">{% endif %}
      {% if e.error %}<p style="color:var(--acento)">{{ e.error }}</p>{% endif %}
      {% if editable %}
        <form hx-post="/api/proyectos/{{ p.id }}/escenas/{{ e.id }}" hx-ext="json-enc" hx-swap="none">
          <textarea name="narracion">{{ e.narracion }}</textarea>
          <input name="imagen_prompt" value="{{ e.imagen_prompt }}">
          <input name="movimiento_prompt" value="{{ e.movimiento_prompt }}">
          <button class="sec">Guardar</button>
        </form>
        {% for clave, txt in [("guion","↻ texto"),("imagen","↻ imagen"),("clip","↻ clip"),("audio","↻ voz")] %}
          <button class="sec" hx-post="/api/proyectos/{{ p.id }}/escenas/{{ e.id }}/regenerar/{{ clave }}"
            hx-on::after-request="location.reload()">{{ txt }}</button>
        {% endfor %}
      {% else %}<p>{{ e.narracion }}</p>{% endif %}
    </div>
  {% endfor %}
  </div>
</div>
{% endfor %}
```

`app/templates/_revision.html`:
```html
<div class="tarjeta">
  <h2>⏸ Revisión final</h2>
  <video src="/media/{{ p.id }}/final.mp4" controls style="width:100%;max-width:960px;border-radius:8px"></video>
  {% if p.montaje.avisos %}<p style="color:var(--aviso)">Avisos: {{ p.montaje.avisos|join(" · ") }}</p>{% endif %}
  <form hx-post="/api/proyectos/{{ p.id }}/aprobar-final" hx-ext="json-enc" hx-on::after-request="location.reload()">
    <h3>Título</h3>
    {% for t in p.publicacion.titulos %}<label style="display:block"><input type="radio" name="titulo" value="{{ t }}" style="width:auto" {% if loop.first %}checked{% endif %}> {{ t }}</label>{% endfor %}
    <h3>Miniatura</h3>
    <div class="rejilla">{% for m in p.publicacion.miniaturas %}
      <label><input type="radio" name="miniatura" value="{{ m }}" style="width:auto" {% if loop.first %}checked{% endif %}>
        <img src="/media/{{ p.id }}/{{ m }}" style="width:100%;border-radius:6px"></label>{% endfor %}</div>
    <h3>Descripción</h3><pre style="white-space:pre-wrap" class="tenue">{{ p.publicacion.descripcion }}</pre>
    <div style="display:flex;gap:12px;max-width:600px">
      <label>Privacidad<select name="privacidad"><option value="private">Privado</option><option value="unlisted">Oculto</option><option value="public">Público</option></select></label>
      <label>Programar (opcional, ISO 8601 UTC)<input name="publicar_en" placeholder="2026-10-20T16:00:00Z"></label>
    </div><br>
    <button>🚀 Aprobar y publicar en YouTube</button>
  </form>
</div>
```
(Nota: con `json-enc`, `publicar_en` vacío llega como `""`; en `app/api.py::aprobar_final` convertir `datos.publicar_en or None`.)

`app/templates/ajustes.html`:
```html
{% extends "base.html" %}
{% block contenido %}
<div class="tarjeta"><h2>Ajustes</h2>
  <p>Modo: <b>{{ aj.modo }}</b> (cámbialo en <code>.env</code> → <code>DV_MODO</code> y reinicia)</p>
  <h3>Claves</h3>{% for n, ok in claves.items() %}<div>{{ "✅" if ok else "⬜" }} {{ n }}</div>{% endfor %}
  <p class="tenue">Las claves se editan en el archivo <code>.env</code>; la app nunca las muestra.</p>
  <h3>Modelos</h3><div>Guion: {{ aj.modelo_guion }} · Supervisor: {{ aj.modelo_supervisor }}</div>
  <div>Imagen: {{ aj.fal_imagen }}</div><div>Vídeo barato: {{ aj.fal_video_barato }} · premium: {{ aj.fal_video_premium }}</div>
  <div>Voz: {{ aj.tts }}</div>
  <h3>Precios usados para estimar</h3><pre class="tenue">{{ precios }}</pre>
  <h3>YouTube</h3>
  {% if youtube %}✅ Canal conectado{% else %}
    <form method="post" action="/ajustes/youtube"><button>Conectar YouTube</button></form>
    <p class="tenue">Se abrirá el navegador para que autorices tu canal. Necesitas <code>{{ aj.youtube_client_secret }}</code> (credenciales OAuth de escritorio de Google Cloud).</p>
  {% endif %}
</div>
{% endblock %}
```

`run.py`:
```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:crear_app", factory=True, host="127.0.0.1", port=8000)
```

- [ ] **Step 5: Run** `pytest tests/test_web.py -v` → PASS; `pytest -v` → PASS
- [ ] **Step 6: Prueba manual** — `.venv\Scripts\python run.py`, abrir `http://127.0.0.1:8000`, crear proyecto de 1 min en modo simulado, aprobar guion, ver vídeo final, aprobar publicación. Comprobar que la línea de tiempo se actualiza sola.
- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: interfaz web htmx"`

---

### Task 16: README y prueba real de 1 minuto

**Files:**
- Create: `README.md`

- [ ] **Step 1: Escribir README** con: requisitos (Python 3.11, FFmpeg), instalación (`python -m venv .venv`, `pip install -e .[dev]`), copiar `.env.example` a `.env`, modo simulado vs real, cómo obtener cada clave (Anthropic Console, fal.ai dashboard, ElevenLabs, Google Cloud → API YouTube Data v3 → credencial OAuth “App de escritorio” → `client_secret.json`), `python run.py`, flujo con los dos ⏸, dónde quedan los archivos (`proyectos/<id>/`), y aviso de costes orientativos.

- [ ] **Step 2: Suite completa** `pytest -v` → todo PASS. Pegar el resumen en el mensaje de commit.

- [ ] **Step 3: Commit** `git add -A && git commit -m "docs: README"`

- [ ] **Step 4: Prueba real (la ejecuta el usuario con sus claves)** — `DV_MODO=real`, proyecto de 1 min, presupuesto 8 $, privacidad *Privado*. Verificar: guion coherente, 5 imágenes, 5 clips, audio, `final.mp4` ≈1 min, coste real en el panel ≤ estimación × 1,5, vídeo privado en YouTube con miniatura y subtítulos. Anotar desviaciones de precio y actualizar `PRECIOS`.
