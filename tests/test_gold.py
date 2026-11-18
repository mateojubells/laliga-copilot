from eval import gold_tools as G


def test_gold_is_valid():
    assert G.validate() == []


def test_split_by_group_is_stable_and_mixed():
    groups = [f"plantilla-{i}" for i in range(400)]
    splits = [G.split_for_group(g) for g in groups]
    assert splits == [G.split_for_group(g) for g in groups]
    assert 0.3 < splits.count("test") / len(splits) < 0.5
