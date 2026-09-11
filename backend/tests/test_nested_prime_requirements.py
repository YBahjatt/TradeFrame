from app.schemas.dto import InventoryRow
from app.services.collection import CollectionService


def row(
    name: str,
    parent: str,
    required: int,
    owned: int,
    tradable: int,
    component_type: str = "relic_reward",
) -> InventoryRow:
    return InventoryRow(
        unique_name=name,
        name=name,
        category="prime_craft",
        parent_name=parent,
        component_type=component_type,
        item_type="Secondary",
        vaulted=True,
        mastered=False,
        owned_count=owned,
        required_count=required,
        tradable_count=tradable,
        direct_count=owned,
        pending_count=0,
        component_count=0,
        safe_to_trade=tradable,
        market_value=1,
        collection_value=0,
    )


def test_nested_prime_requirement_expands_to_child_parts() -> None:
    service = CollectionService.__new__(CollectionService)
    magnus = {
        "parent_name": "Magnus Prime",
        "base": row("Magnus Prime", "Magnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Magnus Prime Blueprint", "Magnus Prime", 1, 1, 1, "0"),
            row("Magnus Prime Barrel", "Magnus Prime", 1, 1, 1),
            row("Magnus Prime Receiver", "Magnus Prime", 1, 1, 1),
        ],
    }
    akmagnus = {
        "parent_name": "Akmagnus Prime",
        "base": row("Akmagnus Prime", "Akmagnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Akmagnus Prime Blueprint", "Akmagnus Prime", 1, 1, 1, "0"),
            row("Akmagnus Prime Link", "Akmagnus Prime", 1, 1, 1),
            row("Magnus Prime", "Akmagnus Prime", 2, 0, 0, "nested_prime_requirement"),
        ],
    }
    groups = {"Magnus Prime": magnus, "Akmagnus Prime": akmagnus}

    parts = {part.name: part for part in service._effective_set_math_parts(akmagnus, groups)}

    assert parts["Akmagnus Prime Blueprint"].required_count == 1
    assert parts["Akmagnus Prime Link"].required_count == 1
    assert parts["Magnus Prime Blueprint"].required_count == 2
    assert parts["Magnus Prime Barrel"].required_count == 2
    assert parts["Magnus Prime Receiver"].required_count == 2


def test_nested_prime_requirement_reserves_child_parts_from_trading() -> None:
    service = CollectionService.__new__(CollectionService)
    magnus = {
        "parent_name": "Magnus Prime",
        "base": row("Magnus Prime", "Magnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Magnus Prime Blueprint", "Magnus Prime", 1, 2, 2, "0"),
            row("Magnus Prime Barrel", "Magnus Prime", 1, 2, 2),
            row("Magnus Prime Receiver", "Magnus Prime", 1, 2, 2),
        ],
    }
    akmagnus = {
        "parent_name": "Akmagnus Prime",
        "base": row("Akmagnus Prime", "Akmagnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Akmagnus Prime Blueprint", "Akmagnus Prime", 1, 1, 1, "0"),
            row("Akmagnus Prime Link", "Akmagnus Prime", 1, 1, 1),
            row("Magnus Prime", "Akmagnus Prime", 2, 0, 0, "nested_prime_requirement"),
        ],
    }
    groups = {"Magnus Prime": magnus, "Akmagnus Prime": akmagnus}

    reservations = service._nested_part_reservations(groups)

    assert reservations["Magnus Prime Blueprint"] == 2
    assert CollectionService._first_build_tradable_surplus(magnus["parts"][0], 3) == 0


def test_nested_prime_requirement_counts_built_child_and_spare_set() -> None:
    service = CollectionService.__new__(CollectionService)
    magnus = {
        "parent_name": "Magnus Prime",
        "base": row("Magnus Prime", "Magnus Prime", 1, 1, 0, "parent"),
        "built": True,
        "mastered": True,
        "parts": [
            row("Magnus Prime Blueprint", "Magnus Prime", 1, 1, 1, "0"),
            row("Magnus Prime Barrel", "Magnus Prime", 1, 1, 1),
            row("Magnus Prime Receiver", "Magnus Prime", 1, 1, 1),
        ],
    }
    akmagnus = {
        "parent_name": "Akmagnus Prime",
        "base": row("Akmagnus Prime", "Akmagnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Akmagnus Prime Blueprint", "Akmagnus Prime", 1, 1, 1, "0"),
            row("Akmagnus Prime Link", "Akmagnus Prime", 1, 1, 1),
            row("Magnus Prime", "Akmagnus Prime", 2, 0, 0, "nested_prime_requirement"),
        ],
    }
    groups = {"Magnus Prime": magnus, "Akmagnus Prime": akmagnus}

    parts = {part.name: part for part in service._effective_set_math_parts(akmagnus, groups)}
    reservations = service._nested_part_reservations(groups)

    assert parts["Magnus Prime Blueprint"].required_count == 1
    assert parts["Magnus Prime Barrel"].required_count == 1
    assert parts["Magnus Prime Receiver"].required_count == 1
    assert all(part.owned_count >= part.required_count for part in parts.values())
    assert reservations["Magnus Prime Blueprint"] == 1
    assert reservations["Magnus Prime Barrel"] == 1
    assert reservations["Magnus Prime Receiver"] == 1
    assert CollectionService._built_item_tradable_surplus(magnus["parts"][0], False, reservations["Magnus Prime Blueprint"]) == 0


def test_nested_prime_requirement_shows_quantity_for_all_missing_child_sets() -> None:
    service = CollectionService.__new__(CollectionService)
    magnus = {
        "parent_name": "Magnus Prime",
        "base": row("Magnus Prime", "Magnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Magnus Prime Blueprint", "Magnus Prime", 1, 0, 0, "0"),
            row("Magnus Prime Barrel", "Magnus Prime", 1, 0, 0),
            row("Magnus Prime Receiver", "Magnus Prime", 1, 0, 0),
        ],
    }
    akmagnus = {
        "parent_name": "Akmagnus Prime",
        "base": row("Akmagnus Prime", "Akmagnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Akmagnus Prime Blueprint", "Akmagnus Prime", 1, 1, 1, "0"),
            row("Akmagnus Prime Link", "Akmagnus Prime", 1, 1, 1),
            row("Magnus Prime", "Akmagnus Prime", 2, 0, 0, "nested_prime_requirement"),
        ],
    }
    groups = {"Magnus Prime": magnus, "Akmagnus Prime": akmagnus}

    complete_count, partial_sets = CollectionService._first_set_details(service._effective_set_math_parts(akmagnus, groups))

    assert complete_count == 0
    assert partial_sets == [
        {
            "Magnus Prime Barrel": 2,
            "Magnus Prime Blueprint": 2,
            "Magnus Prime Receiver": 2,
        }
    ]


def test_nested_prime_requirement_copy_text_excludes_nested_parent_item() -> None:
    service = CollectionService.__new__(CollectionService)
    magnus = {
        "parent_name": "Magnus Prime",
        "base": row("Magnus Prime", "Magnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Magnus Prime Blueprint", "Magnus Prime", 1, 0, 0, "0"),
            row("Magnus Prime Barrel", "Magnus Prime", 1, 0, 0),
            row("Magnus Prime Receiver", "Magnus Prime", 1, 0, 0),
        ],
    }
    akmagnus = {
        "parent_name": "Akmagnus Prime",
        "base": row("Akmagnus Prime", "Akmagnus Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Akmagnus Prime Blueprint", "Akmagnus Prime", 1, 1, 1, "0"),
            row("Akmagnus Prime Link", "Akmagnus Prime", 1, 1, 1),
            row("Magnus Prime", "Akmagnus Prime", 2, 0, 0, "nested_prime_requirement"),
        ],
    }
    groups = {"Magnus Prime": magnus, "Akmagnus Prime": akmagnus}

    _, partial_sets = CollectionService._first_set_details(service._effective_set_math_parts(akmagnus, groups))
    copy_parts = [
        f"{part.chat_text} x{part.quantity}"
        for part in CollectionService._collection_missing_parts(partial_sets[0])
    ]
    copy_text = CollectionService._copy_part_list(copy_parts)

    assert "[Magnus Prime] x2" not in copy_text
    assert "[Magnus Prime] BP x2" in copy_text
    assert "[Magnus Prime Barrel] x2" in copy_text
    assert "[Magnus Prime Receiver] x2" in copy_text


def test_nested_prime_requirement_applies_to_aklex_style_builds() -> None:
    service = CollectionService.__new__(CollectionService)
    lex = {
        "parent_name": "Lex Prime",
        "base": row("Lex Prime", "Lex Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Lex Prime Blueprint", "Lex Prime", 1, 0, 0, "0"),
            row("Lex Prime Barrel", "Lex Prime", 1, 0, 0),
            row("Lex Prime Receiver", "Lex Prime", 1, 0, 0),
        ],
    }
    aklex = {
        "parent_name": "Aklex Prime",
        "base": row("Aklex Prime", "Aklex Prime", 1, 0, 0, "parent"),
        "built": False,
        "mastered": False,
        "parts": [
            row("Aklex Prime Blueprint", "Aklex Prime", 1, 1, 1, "0"),
            row("Aklex Prime Link", "Aklex Prime", 1, 1, 1),
            row("Lex Prime", "Aklex Prime", 2, 0, 0, "nested_prime_requirement"),
        ],
    }
    groups = {"Lex Prime": lex, "Aklex Prime": aklex}

    parts = {part.name: part for part in service._effective_set_math_parts(aklex, groups)}
    _, partial_sets = CollectionService._first_set_details(list(parts.values()))
    copy_parts = [
        f"{part.chat_text} x{part.quantity}"
        for part in CollectionService._collection_missing_parts(partial_sets[0])
    ]
    copy_text = CollectionService._copy_part_list(copy_parts)

    assert parts["Lex Prime Blueprint"].required_count == 2
    assert parts["Lex Prime Barrel"].required_count == 2
    assert parts["Lex Prime Receiver"].required_count == 2
    assert "[Lex Prime] x2" not in copy_text
    assert "[Lex Prime] BP x2" in copy_text
    assert "[Lex Prime Barrel] x2" in copy_text
    assert "[Lex Prime Receiver] x2" in copy_text
