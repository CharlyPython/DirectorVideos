# DirectorVideos

App local (FastAPI + htmx) que convierte una idea en un vídeo de YouTube sin cara. Un **Arquitecto** (Claude, supervisor) planifica; un **Director** (máquina de estados) coordina seis agentes: Guionista, Ilustrador, Animador, Narrador, Montador y Publicador. Hay **dos aprobaciones humanas**.

## Requisitos

- Windows con **Python 3.11+**.
- **FFmpeg y ffprobe en el PATH**, compilado con `libx264`, `libmp3lame` y `libass` (subtítulos). Comprueba con `ffmpeg -version`.

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

Si pip da errores de certificado SSL (proxy corporativo o antivirus), añade `--use-feature=truststore`.

Copia la configuración:

```powershell
copy .env.example .env
```

## Modo simulado vs real

`DV_MODO` en `.env`:

- `simulado` (por defecto): proveedores falsos, **sin coste y sin claves**. Útil para probar el flujo y la interfaz.
- `real`: usa las APIs de pago. Si falta alguna clave, la app indica cuáles en `.env`.

## Claves (modo real)

| Variable | Dónde obtenerla |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console (console.anthropic.com) → API Keys. |
| `FAL_KEY` | Panel de fal.ai → Keys (imágenes y clips de vídeo). |
| `ELEVENLABS_API_KEY` + `DV_ELEVENLABS_VOZ` | ElevenLabs: API key de tu perfil y el *voice id* de la voz elegida. Con `DV_TTS=elevenlabs`. |
| `OPENAI_API_KEY` (+ `DV_OPENAI_VOZ`, por defecto `onyx`) | Alternativa de voz: pon `DV_TTS=openai`. |
| YouTube (OAuth) | Ver abajo. |

Modelos de Claude por defecto: `DV_MODELO_GUION=claude-sonnet-5-5` (guion) y `DV_MODELO_SUPERVISOR=claude-opus-5-5` (supervisor). También son configurables `DV_FAL_IMAGEN`, `DV_FAL_VIDEO_BARATO`, `DV_FAL_VIDEO_PREMIUM`, `DV_RAIZ` (carpeta de proyectos, `proyectos`) y `DV_CONCURRENCIA` (1–10, por defecto 6).

**YouTube:**

1. En Google Cloud Console crea un proyecto y activa **YouTube Data API v3**.
2. Crea una credencial **ID de cliente OAuth** de tipo **App de escritorio**.
3. Descarga el JSON como `client_secret.json` en la carpeta del proyecto (o apunta `DV_YOUTUBE_CLIENT_SECRET` a otra ruta).
4. Arranca la app, ve a **Ajustes → Conectar YouTube** y autoriza. El token queda en `token_youtube.json`.

`.env`, `client_secret*.json`, `token_youtube.json` y `proyectos/` están en `.gitignore`. No subas claves al repositorio.

## Ejecutar

```powershell
.venv\Scripts\python run.py
```

Abre http://127.0.0.1:8000.

## Flujo

1. Creas un proyecto (idea, duración, plan de vídeo, presupuesto, privacidad).
2. El Guionista genera el guion y el desglose en escenas.
3. **⏸1 Aprobación del guion**: revisas y editas escenas, regeneras capítulos y apruebas.
4. Se generan **5 imágenes por minuto** y un **clip IA de 10 s** por escena (barato o premium según el plan), además de la narración y el montaje con subtítulos.
5. **⏸2 Aprobación del vídeo final**: ves el resultado, puedes regenerar escenas y apruebas.
6. El Publicador genera metadatos y 3 miniaturas y sube el vídeo a YouTube con la privacidad elegida.

**Presupuesto:** si el gasto alcanza el tope, el proyecto se **pausa**. Sube el presupuesto en el panel del proyecto y pulsa **Reanudar**.

## Archivos generados

Todo queda en `proyectos/<id>/`:

- `guion.json`
- `imagenes/`, `clips/`, `audio/`
- `final.mp4` y `subtitulos.srt`
- `miniatura_*.png`
- `informe.md`

## Costes

Los precios de `core/costes.py` (y los de `proveedores/fabrica.py`) son **orientativos**; verifícalos con cada proveedor. Ejemplos: ~0,025 $ por imagen, ~0,30 $ (barato) a ~1,00 $ (premium) por clip de 10 s, ~0,30 $/min de voz, ~0,20 $ de publicación. Los clips dominan el coste.

**Primera prueba real recomendada:** proyecto de **1 minuto**, presupuesto **~8 $**, privacidad **Privado**. Compara el coste real del panel con la estimación y ajusta `PRECIOS` si hay desviaciones.

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

Tardan varios minutos: usan proveedores simulados pero FFmpeg real.

## API JSON (fase 2: integración con Hermes)

La interfaz web usa una API JSON bajo `/api`, pensada para integrar un agente externo (Hermes) más adelante:

- `GET /api/proyectos`, `POST /api/proyectos`, `GET /api/proyectos/{pid}`
- `POST /api/proyectos/{pid}/aprobar-guion` y `/aprobar-final`
- `POST /api/proyectos/{pid}/reanudar` y `/presupuesto`
- `POST /api/proyectos/{pid}/escenas/{eid}` y `/escenas/{eid}/regenerar/{clave}`
- `POST /api/proyectos/{pid}/capitulos/{numero}/regenerar`
- `GET /api/proyectos/{pid}/eventos` (SSE con el progreso)

Documentación interactiva de FastAPI en http://127.0.0.1:8000/docs.
