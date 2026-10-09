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
