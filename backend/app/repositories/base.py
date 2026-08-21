from sqlalchemy import select
from sqlalchemy.orm import Session
import re

from app.models.entities import Inventory, Item, MarketPrice, ScoringWeight, Trade


class ItemRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, item: Item) -> Item:
        existing = self.db.scalar(select(Item).where(Item.unique_name == item.unique_name))
        if existing:
            for field in ("name", "category", "parent_name", "component_type", "vaulted", "tradable", "required_count", "image"):
                setattr(existing, field, getattr(item, field))
            return existing
        self.db.add(item)
        self.db.flush()
        return item

    def all_prime_parts(self) -> list[Item]:
        stmt = select(Item).where(Item.tradable.is_(True)).order_by(Item.category, Item.name)
        return list(self.db.scalars(stmt))


class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, item_id: int, owned_count: int, tradable_count: int, mastered: bool, raw: str | None = None) -> None:
        existing = self.db.scalar(select(Inventory).where(Inventory.item_id == item_id))
        if existing:
            existing.owned_count = owned_count
            existing.tradable_count = tradable_count
            existing.mastered = mastered
            existing.raw = raw
            return
        self.db.add(Inventory(item_id=item_id, owned_count=owned_count, tradable_count=tradable_count, mastered=mastered, raw=raw))


class PriceRepository:
    def __init__(self, db: Session):
        self.db = db

    def price_for_item(self, item_id: int) -> MarketPrice | None:
        return self.db.scalar(select(MarketPrice).where(MarketPrice.item_id == item_id).order_by(MarketPrice.updated_at.desc()))

    def upsert_price(self, item_id: int, current_price: float, average_price: float, source: str = "warframe.market") -> None:
        existing = self.db.scalar(select(MarketPrice).where(MarketPrice.item_id == item_id, MarketPrice.source == source))
        if existing:
            existing.current_price = current_price
            existing.average_price = average_price
            return
        self.db.add(MarketPrice(item_id=item_id, current_price=current_price, average_price=average_price, source=source))


class WeightRepository:
    def __init__(self, db: Session):
        self.db = db

    def as_dict(self) -> dict[str, int]:
        return {row.key: row.value for row in self.db.scalars(select(ScoringWeight))}


class TradeRepository:
    AUTO_DUPLICATE_SECONDS = 120

    def __init__(self, db: Session):
        self.db = db

    def upsert(self, trade: Trade) -> None:
        existing = self.db.scalar(select(Trade).where(Trade.source == trade.source, Trade.source_line == trade.source_line))
        if existing:
            for field in ("traded_at", "partner", "classification", "given_text", "received_text"):
                setattr(existing, field, getattr(trade, field))
            return
        self.db.add(trade)

    def all(self) -> list[Trade]:
        return self.analysis_rows()

    def analysis_rows(self) -> list[Trade]:
        rows = self._ordered_rows()
        result: list[Trade] = []
        last_visible_by_key: dict[tuple[str, str, str, str], Trade] = {}
        for row in sorted(rows, key=self._chronological_sort_key):
            if row.duplicate_decision == "deleted":
                continue
            key = self._dedupe_key(row)
            previous = last_visible_by_key.get(key)
            if previous is not None and self._time_gap_seconds(row, previous) <= self.AUTO_DUPLICATE_SECONDS:
                if previous.duplicate_decision != "confirmed" and previous in result:
                    result.remove(previous)
                last_visible_by_key[key] = row
                result.append(row)
                continue
            last_visible_by_key[key] = row
            result.append(row)
        return list(reversed(result))

    def duplicate_review_info(self, trade: Trade) -> tuple[bool, int | None]:
        if trade.duplicate_decision in {"confirmed", "deleted"}:
            return False, None
        key = self._dedupe_key(trade)
        rows = sorted(self._ordered_rows(), key=self._chronological_sort_key)
        for index, row in enumerate(rows):
            if row.id == trade.id:
                for candidate in rows[index + 1:]:
                    if candidate.duplicate_decision == "deleted":
                        continue
                    if self._dedupe_key(candidate) == key:
                        gap = self._time_gap_seconds(candidate, trade)
                        return gap > self.AUTO_DUPLICATE_SECONDS, gap
                    return False, None
            if row.duplicate_decision == "deleted":
                continue
        return False, None

    def set_duplicate_decision(self, trade_id: int, decision: str) -> bool:
        trade = self.db.get(Trade, trade_id)
        if trade is None:
            return False
        trade.duplicate_decision = decision
        self.db.commit()
        return True

    def _ordered_rows(self) -> list[Trade]:
        return sorted(
            self.db.scalars(select(Trade)).all(),
            key=lambda row: (row.traded_at is not None, row.traded_at, self._cleanliness_score(row)),
            reverse=True,
        )

    @staticmethod
    def _chronological_sort_key(row: Trade) -> tuple[bool, object, int]:
        return (row.traded_at is not None, row.traded_at or "", -TradeRepository._cleanliness_score(row))

    @staticmethod
    def _dedupe_key(trade: Trade) -> tuple[str, str, str, str]:
        given_text, received_text = TradeRepository._canonical_trade_texts(trade)
        return (
            TradeRepository._normalize_trade_text(trade.partner),
            (trade.classification or "").strip().lower(),
            TradeRepository._normalize_trade_text(given_text),
            TradeRepository._normalize_trade_text(received_text),
        )

    @staticmethod
    def _normalize_trade_text(value: str | None) -> str:
        text = "".join(ch for ch in (value or "") if ord(ch) < 57344 or ord(ch) > 63743)
        return " ".join(text.lower().split())

    @staticmethod
    def _within_duplicate_window(candidate: Trade, existing: Trade) -> bool:
        if candidate.traded_at is None or existing.traded_at is None:
            return True
        return abs((existing.traded_at - candidate.traded_at).total_seconds()) <= TradeRepository.AUTO_DUPLICATE_SECONDS

    @staticmethod
    def _time_gap_seconds(candidate: Trade, existing: Trade) -> int:
        if candidate.traded_at is None or existing.traded_at is None:
            return 0
        return int(abs((candidate.traded_at - existing.traded_at).total_seconds()))

    @staticmethod
    def _cleanliness_score(trade: Trade) -> int:
        return int(bool((trade.given_text or "").strip())) + int("and will receive from" not in (trade.received_text or ""))

    @staticmethod
    def _canonical_trade_texts(trade: Trade) -> tuple[str, str]:
        given_text = (trade.given_text or "").strip()
        received_text = (trade.received_text or "").strip()
        if not given_text and "and will receive from" in received_text:
            match = re.match(r"(?P<given>.*?)\band will receive from\b.*?\bthe following:\s*(?P<received>.*)", received_text, flags=re.I | re.S)
            if match:
                given_text = match.group("given").strip()
                received_text = re.sub(r",?\s*title=.*$", "", match.group("received").strip(), flags=re.I | re.S)
        return given_text, received_text
