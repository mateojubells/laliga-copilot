"""Public-copy adjustments: tests that need the private evaluation data are not collected.

The evaluation gold data (annotated match audio transcripts) is not published in this repository,
so the tests that depend on it are skipped at collection time.
"""
from pathlib import Path

_GOLD = Path(__file__).parent / "eval" / "gold" / "barca-valladolid.truth.json"

collect_ignore = []
if not _GOLD.exists():
    collect_ignore += ["data/synth/test_truth.py", "tests/test_gold.py", "tests/test_metrics.py"]


def pytest_collection_modifyitems(config, items):
    import pytest

    if _GOLD.exists():
        return
    skip = pytest.mark.skip(reason="needs private evaluation data (eval/gold), not published")
    for item in items:
        if "reference_match_ids" in item.name:
            item.add_marker(skip)
