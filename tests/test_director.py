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


async def test_regenerar_completado_rechazado_y_sube_una_vez(raiz):
    d = _director(raiz)
    pid = await d.crear("Roma", 1, "documental", 50)
    await d.avanzar(pid); d.aprobar_guion(pid); await d.avanzar(pid)
    pub = d.almacen.cargar_json(pid, "publicacion.json")
    d.aprobar_final(pid, pub["titulos"][0], pub["miniaturas"][0])
    assert await d.avanzar(pid) == Fase.COMPLETADO
    with pytest.raises(ValueError):
        await d.regenerar(pid, "c01_s001", "imagen")
    with pytest.raises(ValueError):
        await d.regenerar_capitulo(pid, 1)
    assert d.almacen.fase(pid) == Fase.COMPLETADO and len(d.proveedores.subidor.subidas) == 1


async def test_regenerar_imagen_antes_de_aprobar_guion(raiz):
    d = _director(raiz)
    pid = await d.crear("Roma", 1, "documental", 50)
    await d.avanzar(pid)
    for clave in ("imagen", "clip", "audio", "otra"):
        with pytest.raises(ValueError):
            await d.regenerar(pid, "c01_s001", clave)
    with pytest.raises(ValueError):
        await d.regenerar(pid, "nope", "guion")


async def test_ocupado_durante_regenerar(raiz):
    import asyncio
    prov = proveedores_simulados()
    interno, entrada, suelta = prov.imagen, asyncio.Event(), asyncio.Event()
    class Lenta:
        def __init__(self): self.activa = False
        async def generar(self, prompt, destino):
            if self.activa:
                entrada.set(); await suelta.wait()
            return await interno.generar(prompt, destino)
    prov.imagen = lenta = Lenta()
    d = _director(raiz, prov)
    pid = await d.crear("Roma", 1, "documental", 50)
    await d.avanzar(pid); d.aprobar_guion(pid); await d.avanzar(pid)
    lenta.activa = True
    t = asyncio.create_task(d.regenerar(pid, "c01_s001", "imagen"))
    await entrada.wait()
    assert d.ocupado(pid)
    with pytest.raises(ValueError):
        await d.regenerar(pid, "c01_s002", "imagen")
    d.lanzar(pid)                      # ignorado: sigue ocupado
    suelta.set(); await t
    assert not d.ocupado(pid)
