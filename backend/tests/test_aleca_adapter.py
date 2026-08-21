import json
from pathlib import Path

from app.adapters.aleca import AlecaAdapter


def test_reference_item_extraction_keeps_prime_items() -> None:
    payload = {
        "items": {
            "/Lotus/Types/Recipes/Weapons/WeaponParts/ParisPrimeString": {
                "name": "Paris Prime String",
                "vaulted": True,
                "tradeable": True,
            },
            "/Lotus/Weapons/Tenno/LongGuns/RegularThing": {"name": "Regular Thing"},
        }
    }
    rows = AlecaAdapter._extract_reference_items(payload, "Primary")
    assert len(rows) == 1
    assert rows[0]["name"] == "Paris Prime String"
    assert rows[0]["vaulted"] is True


def test_trade_line_parser() -> None:
    line = "Trade log processed: ts: 08/12/2026 23:35:52, tx: 1, rx: 1, user: SoLeahLicious Classification: Purchase"
    parsed = AlecaAdapter._parse_trade_processed(line)
    assert parsed["partner"] == "SoLeahLicious"
    assert parsed["classification"] == "Purchase"
