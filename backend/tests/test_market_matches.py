from datetime import datetime, timedelta, timezone

from app.services.market_matches import MarketMatchService


def test_online_market_status_goes_offline_when_last_seen_is_stale() -> None:
    now = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
    last_seen = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    assert MarketMatchService._fresh_status("ingame", last_seen, now) == "offline"


def test_recent_market_status_stays_online() -> None:
    now = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
    last_seen = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    assert MarketMatchService._fresh_status("online", last_seen, now) == "online"
