import pytest
from pathlib import Path

@pytest.fixture
def raiz(tmp_path) -> Path:
    return tmp_path / "proyectos con espacio y ñ"
