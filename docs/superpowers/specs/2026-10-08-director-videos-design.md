# DirectorVideos — Especificación de diseño

Fecha: 2026-10-08 · Estado: pendiente de revisión

## 1. Objetivo

Aplicación local que produce vídeos largos (5–50 min) para un canal **faceless** de YouTube a partir de una idea: guion, imágenes, vídeos y voz generados con IA, montaje automático y publicación. Inicialmente con dos puntos de aprobación humana (guion y vídeo final).

**Criterios de éxito**
- Desde una idea, la app produce un `final.mp4` 1080p publicable sin edición manual.
- El usuario aprueba el guion y el vídeo final antes de publicar; nada se publica sin aprobación.
- El coste estimado se muestra antes de gastar; existe un tope duro por proyecto.
- Un fallo en cualquier paso se reanuda sin volver a pagar lo ya generado.

**Fuera de alcance (fase 1)**: acceso remoto/móvil, modo totalmente automático, integración con Hermes (fase 2), formato Shorts.

## 2. Arquitectura

```
Navegador (localhost:8000) — Panel · Editor guion · Producción · Revisión · Ajustes
                    │ HTTP + progreso en vivo (SSE)
Backend FastAPI
 ├─ 🧠 ARQUITECTO (Claude) — planifica, revisa calidad, controla presupuesto, decide
 ├─ 🎬 DIRECTOR (código determinista) — secuencia, estados, colas, costes, pausas ⏸, reintentos
 ├─ Agentes: 1 Guionista → 2 Ilustrador → 3 Animador → 4 Narrador → 5 Montador → 6 Publicador
 └─ Proveedores intercambiables (Claude, fal.ai, ElevenLabs/OpenAI, FFmpeg, YouTube API)
Persistencia: SQLite (proyectos, estados, costes) + carpetas en disco por proyecto
```

- Python 3.11+, FastAPI, htmx en la interfaz, SQLite, cola de tareas asíncrona en proceso (sin Redis/Docker). Requiere FFmpeg instalado.
- Claves de API en `.env`, introducidas por el usuario.
- API REST limpia del motor (crear proyecto, estado, aprobar, regenerar) para que Hermes se conecte en fase 2 hablando con el Arquitecto.

## 3. Roles

### 3.1 Arquitecto (supervisor, Claude)
1. **Plan de producción** a partir de la idea: duración, estilo visual, voz, modelo de vídeo, presupuesto máximo, enfoque YouTube (audiencia, ángulo). Se presenta junto al guion en el ⏸1.
2. **Control de calidad** entre agentes: duración/repeticiones del guion; coherencia de imágenes con la biblia visual (visión de Claude, por muestreo); clips defectuosos. Ordena al Director regenerar escenas concretas.
3. **Presupuesto**: si el gasto se acerca al tope, pausa y pregunta.
4. **Informe final** (`informe.md`): qué se hizo, coste, regeneraciones y motivo.

Límites: máximo 2 regeneraciones por escena; nunca salta un ⏸ ni publica sin aprobación.

### 3.2 Director (motor, sin IA)
Máquina de estados por proyecto. Lanza agentes en orden, gestiona concurrencia (5–10 generaciones simultáneas), reintentos, contabilidad de costes, pausas y reanudación. Ejecuta las órdenes del Arquitecto.

### 3.3 Contrato común de agentes
- Interfaz: `ejecutar(proyecto) -> Resultado` con eventos de progreso, coste y errores.
- Solo leen la salida del agente anterior en la carpeta del proyecto.
- Reanudables a nivel de escena (estado por escena).
- Relanzables de forma aislada (p. ej. “solo el Narrador con otra voz”).
- **Modo simulado** (sin llamadas de pago) para pruebas.

## 4. Secuencia

| # | Agente | Entrada | Salida | Proveedor (por defecto) |
|---|---|---|---|---|
| 1 | Guionista | idea, duración, tono, plan | `guion.json` + biblia visual | Claude |
| ⏸1 | Aprobación guion + plan + coste estimado | | | |
| 2 | Ilustrador | escenas + biblia visual | `imagenes/<escena>.png` 1920×1080 | Flux (fal.ai) |
| 3 | Animador | imagen + prompt de movimiento | `clips/<escena>.mp4` de 10 s | Kling/Veo/Hailuo (fal.ai), seleccionable por proyecto (barato / premium) |
| 4 | Narrador | narración por escena | `audio/<escena>.mp3` + duración medida | ElevenLabs u OpenAI TTS |
| 5 | Montador | clips + audios (+ música) | `final.mp4` 1080p + `subtitulos.srt` | FFmpeg |
| ⏸2 | Revisión vídeo, título, descripción, miniatura | | | |
| 6 | Publicador | vídeo + guion | metadatos, miniatura, subida | Claude + YouTube Data API |

### 4.1 Guionista
- Tres pasos: **esquema** (título provisional, gancho 30 s, 5–12 capítulos con duración) → **narración por capítulo** (con contexto previo, ~150 palabras/min) → **desglose en escenas**.
- **Regla fija: 5 escenas por minuto** (≈12 s de narración por escena).
- Esquema de escena:
```json
{
  "id": "c03_s012",
  "capitulo": 3,
  "narracion": "...",
  "imagen_prompt": "...",
  "movimiento_prompt": "slow push-in, smoke drifting",
  "duracion_estimada": 12.0,
  "estado": {"imagen": "pendiente", "clip": "pendiente", "audio": "pendiente"}
}
```
- Biblia visual por proyecto (estilo, paleta, época, personajes recurrentes) añadida a todos los prompts de imagen.
- Editor ⏸1: editar narración/prompts, regenerar capítulo o escena, aprobar.

### 4.2 Ilustrador
Una imagen por escena; Claude puede refinar prompts. Galería en la app con regeneración/edición individual (corregir aquí es barato antes de animar).

### 4.3 Animador
Imagen → clip de 10 s. Paso más caro: progreso visible, caché en disco, regeneración individual.

### 4.4 Narrador
Audio por escena (regrabar una frase sin rehacer todo). Mide la duración real de cada fragmento.

### 4.5 Montador
- Cada clip de 10 s se ajusta a la duración de su audio (≈12 s → ralentizado ~83 %). Rango permitido de ajuste de velocidad: 0,6×–1,3×; fuera de rango se avisa en la revisión.
- Fundidos cortos entre clips; música opcional con *ducking* bajo la voz.
- Subtítulos `.srt` desde el texto y las duraciones; opción de incrustarlos.

### 4.6 Publicador
- Claude genera 3 títulos, descripción, etiquetas y capítulos con marcas de tiempo del montaje.
- 3 miniaturas (imagen IA + texto); el usuario elige en ⏸2.
- Subida como privado o programado, con `.srt`. Solo tras aprobación.
- OAuth de Google realizado por el usuario una vez desde la app; token guardado localmente.

## 5. Costes
- Estimación previa al paso 2 basada en nº de escenas × precio de cada proveedor (tabla de precios configurable).
- Referencia orientativa a verificar: clip 10 s 0,30–1 $ → 50 min (250 clips) ≈ 75–250 $; 5 min ≈ 8–25 $.
- Contabilidad real por llamada; panel por vídeo y acumulado mensual.
- Tope duro por proyecto: al alcanzarlo, todo se pausa.

## 6. Errores
- Reintentos automáticos con espera exponencial (3) ante fallos de red/límite de peticiones.
- Escena fallida → ❌, el resto continúa; botón “Reanudar” reprocesa solo lo pendiente/fallido.
- Log por agente visible en la app.

## 7. Interfaz
- **Panel**: proyectos y estado.
- **Nueva idea**: tema, tono, duración.
- **Línea de tiempo de agentes**: ⏳ en cola / ⚙️ trabajando / ⏸ esperando / ✅ hecho / ❌ error.
- **Editor de guion** (⏸1), **galería** de imágenes y clips, **revisión final** (⏸2), **costes**, **ajustes** (voz, estilo, modelos, música, claves, conexión YouTube).

## 8. Estructura
```
DirectorVideos/
├─ app/            # FastAPI + plantillas htmx
├─ arquitecto/
├─ director/
├─ agentes/        # guionista, ilustrador, animador, narrador, montador, publicador
├─ proveedores/
├─ proyectos/<id>/ # guion.json, imagenes/, clips/, audio/, final.mp4, informe.md
├─ tests/
├─ .env
└─ docs/
```

## 9. Pruebas
- Tests unitarios por agente con proveedores simulados.
- Prueba de la secuencia completa en modo simulado (coste 0).
- Prueba real de 1 minuto (5 escenas, ≈5 $) antes del primer vídeo largo.

## 10. Fase 2 (no incluida)
Hermes como interfaz conversacional (Telegram) conectado al Arquitecto; aprobaciones desde el móvil; programación de producción; modo totalmente automático.
