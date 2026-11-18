import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from data.synth.testing import connect, full_db  # noqa: E402


@pytest.fixture(scope="session")
def db_path():
    return full_db()


@pytest.fixture(scope="session")
def db(db_path):
    c = connect(db_path)
    yield c
    c.close()
