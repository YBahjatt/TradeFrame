from app.models.entities import Item


class ScoringService:
    def __init__(self, weights: dict[str, int]):
        self.weights = weights

    def score_gain(self, item: Item, owned_count: int, missing_before: int = 1) -> int:
        if owned_count > 0:
            return self.weights.get("gain_duplicate", 0)
        score = self.weights.get("new_unique_vaulted_part" if item.vaulted else "new_unique_unvaulted_part", 20)
        score += self.weights.get(f"missing_{missing_before}_to_{max(missing_before - 1, 0)}", 0)
        if missing_before == 1:
            score += self.weights.get("complete_item", 100)
        return score

    def score_loss(self, owned_count: int, required_count: int) -> int:
        if owned_count <= required_count:
            return self.weights.get("lose_last_copy", -1000)
        return self.weights.get("lose_duplicate", 0)
