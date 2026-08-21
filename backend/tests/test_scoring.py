from types import SimpleNamespace

from app.services.scoring import ScoringService


def test_gain_for_new_vaulted_part_includes_missing_reduction() -> None:
    service = ScoringService({"new_unique_vaulted_part": 40, "missing_2_to_1": 60})
    item = SimpleNamespace(vaulted=True)
    assert service.score_gain(item, owned_count=0, missing_before=2) == 100


def test_gain_for_duplicate_is_zero() -> None:
    service = ScoringService({"gain_duplicate": 0, "new_unique_unvaulted_part": 20})
    item = SimpleNamespace(vaulted=False)
    assert service.score_gain(item, owned_count=1, missing_before=1) == 0


def test_losing_last_copy_is_blocked_by_score() -> None:
    service = ScoringService({"lose_last_copy": -1000, "lose_duplicate": 0})
    assert service.score_loss(owned_count=1, required_count=1) == -1000
    assert service.score_loss(owned_count=2, required_count=1) == 0
