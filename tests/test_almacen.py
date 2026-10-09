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


def test_rutas_relativas_ancladas_al_repo(monkeypatch):
    from core.config import Ajustes, RAIZ_REPO
    monkeypatch.delenv("DV_RAIZ", raising=False)
    monkeypatch.delenv("DV_YOUTUBE_CLIENT_SECRET", raising=False)
    a = Ajustes.desde_entorno()
    assert a.raiz == RAIZ_REPO / "proyectos" and a.youtube_client_secret == RAIZ_REPO / "client_secret.json"
