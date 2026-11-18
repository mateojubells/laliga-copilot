import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if not (shutil.which("node") or (ROOT / ".tools/node/bin/node").exists()):
    pytest.skip("node no disponible", allow_module_level=True)

from eval.legacy_engine import LegacyEngine  # noqa: E402


@pytest.fixture(scope="module")
def eng():
    e = LegacyEngine()
    yield e
    e.close()


def ev(eng, text):
    eng.reset()
    r = eng.analyze(text)
    return r, [(e.type, e.modality, e.roles) for e in r.events]


def test_falta_actor_victima(eng):
    _, evs = ev(eng, "falta de Araujo sobre Pedri")
    assert ("falta", "real", {"actor": "barcelona/araujo", "victim": "barcelona/pedri"}) in evs


def test_penalti_sobre(eng):
    _, evs = ev(eng, "penalti sobre Lamine Yamal")
    assert ("penalti", "real", {"victim": "barcelona/lamine-yamal"}) in evs


def test_cambio_out(eng):
    _, evs = ev(eng, "entra Ferran Torres por Lewandowski")
    assert ("cambio", "real", {"actor": "barcelona/ferran-torres", "out": "barcelona/lewandowski"}) in evs


def test_gol_y_entidades(eng):
    r, evs = ev(eng, "gol de Raphinha")
    assert ("gol", "real", {"actor": "barcelona/raphinha"}) in evs
    assert ("player", "barcelona/raphinha") in {(e.type, e.id) for e in r.entities}


def test_reset_y_sin_estado_entre_frases(eng):
    eng.reset()
    assert eng.analyze("buenas tardes a todos").events == []
