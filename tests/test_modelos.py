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
