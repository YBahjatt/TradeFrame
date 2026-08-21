from __future__ import annotations

import json
from http.client import IncompleteRead
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.adapters.aleca import AlecaAdapter
from app.models.entities import Item, Trade
from app.repositories.base import PriceRepository, TradeRepository
from app.schemas.dto import TradeAnalysisItem, TradeAnalysisResponse, TradeAnalysisRow, TradeAnalysisSummary
from app.services.market import MarketPriceService


@dataclass(frozen=True)
class ParsedTradeItem:
    name: str
    quantity: int
    is_platinum: bool = False


class TradeAnalysisService:
    def __init__(self, db: Session, adapter: AlecaAdapter, use_historical: bool = False):
        self.db = db
        self.use_historical = use_historical
        self.adapter = adapter
        self.prices = PriceRepository(db)
        self.items = list(db.query(Item).order_by(Item.name).all())
        self.item_by_name = {item.name.lower(): item for item in self.items}
        self.market_url_names = self.adapter.read_market_url_names()
        for item in self.items:
            if item.name not in self.market_url_names and item.name.endswith(" Prime"):
                self.market_url_names[item.name] = MarketPriceService._set_url_name(item.name)
        self._history_cache: dict[str, list[dict[str, object]]] = {}
        self._quote_cache: dict[str, float] = {}
        self._external_market_names: dict[str, str] | None = None

    def analyze(self) -> TradeAnalysisResponse:
        repository = TradeRepository(self.db)
        trades = repository.analysis_rows()
        rows = [self._with_duplicate_info(self._analyze_trade(trade), trade, repository) for trade in trades]
        self.db.commit()
        summary = TradeAnalysisSummary(
            trades=len(rows),
            total_balance=round(sum(row.balance for row in rows), 2),
            positive_trades=sum(1 for row in rows if self._trade_outcome(row.balance, row.vaulted_balance) == "win"),
            negative_trades=sum(1 for row in rows if self._trade_outcome(row.balance, row.vaulted_balance) == "loss"),
            neutral_trades=sum(1 for row in rows if self._trade_outcome(row.balance, row.vaulted_balance) == "even"),
            mixed_trades=sum(1 for row in rows if self._trade_outcome(row.balance, row.vaulted_balance) == "mixed"),
            vaulted_balance=sum(row.vaulted_balance for row in rows),
            unmatched_items=sum(1 for row in rows for item in [*row.given_items, *row.received_items] if not item.matched),
        )
        return TradeAnalysisResponse(summary=summary, trades=rows)

    @staticmethod
    def _trade_outcome(balance: float, vaulted_balance: int) -> str:
        if balance == 0 and vaulted_balance == 0:
            return "even"
        if (balance > 0 or vaulted_balance > 0) and balance >= 0 and vaulted_balance >= 0:
            return "win"
        if (balance < 0 or vaulted_balance < 0) and balance <= 0 and vaulted_balance <= 0:
            return "loss"
        return "mixed"

    def _analyze_trade(self, trade: Trade) -> TradeAnalysisRow:
        if trade.analysis_priced_at and trade.analysis_given_items and trade.analysis_received_items:
            return self._snapshot_trade_row(trade)

        given_parsed, received_parsed = self._parse_sides(trade)
        given_items = [self._analysis_item(item, trade.traded_at) for item in given_parsed]
        received_items = [self._analysis_item(item, trade.traded_at) for item in received_parsed]
        given_value = round(sum(item.total_value for item in given_items), 2)
        received_value = round(sum(item.total_value for item in received_items), 2)
        calculated_balance = round(received_value - given_value, 2)
        calculated_vaulted = sum(item.quantity for item in received_items if item.vaulted) - sum(item.quantity for item in given_items if item.vaulted)

        trade.market_delta = calculated_balance
        trade.collection_gain = calculated_vaulted
        trade.analysis_given_value = given_value
        trade.analysis_received_value = received_value
        trade.analysis_given_items = self._items_json(given_items)
        trade.analysis_received_items = self._items_json(received_items)
        trade.analysis_priced_at = datetime.utcnow()
        trade.analysis_price_mode = "historical" if self.use_historical else "snapshot"

        return TradeAnalysisRow(
            trade_id=trade.id,
            traded_at=trade.traded_at,
            partner=trade.partner,
            classification=trade.classification,
            given_items=given_items,
            received_items=received_items,
            given_value=given_value,
            received_value=received_value,
            balance=calculated_balance,
            vaulted_balance=int(calculated_vaulted),
        )

    def _snapshot_trade_row(self, trade: Trade) -> TradeAnalysisRow:
        return TradeAnalysisRow(
            trade_id=trade.id,
            traded_at=trade.traded_at,
            partner=trade.partner,
            classification=trade.classification,
            given_items=self._items_from_json(trade.analysis_given_items),
            received_items=self._items_from_json(trade.analysis_received_items),
            given_value=round(float(trade.analysis_given_value or 0), 2),
            received_value=round(float(trade.analysis_received_value or 0), 2),
            balance=round(float(trade.market_delta or 0), 2),
            vaulted_balance=int(trade.collection_gain or 0),
        )

    @staticmethod
    def _with_duplicate_info(row: TradeAnalysisRow, trade: Trade, repository: TradeRepository) -> TradeAnalysisRow:
        review, gap = repository.duplicate_review_info(trade)
        row.duplicate_review = review
        row.duplicate_gap_seconds = gap
        row.duplicate_decision = trade.duplicate_decision
        return row

    @staticmethod
    def _items_json(items: list[TradeAnalysisItem]) -> str:
        return json.dumps([item.model_dump() for item in items])

    @staticmethod
    def _items_from_json(value: str | None) -> list[TradeAnalysisItem]:
        if not value:
            return []
        try:
            raw_items = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw_items, list):
            return []
        return [TradeAnalysisItem(**item) for item in raw_items if isinstance(item, dict)]

    def _analysis_item(self, parsed: ParsedTradeItem, traded_at: datetime | None) -> TradeAnalysisItem:
        if parsed.is_platinum:
            return TradeAnalysisItem(
                name="Platinum",
                quantity=parsed.quantity,
                unit_price=1,
                total_value=float(parsed.quantity),
                vaulted=False,
                matched=True,
            )
        item = self.item_by_name.get(parsed.name.lower())
        if item is None:
            external_name, url_name = self._external_market_match(parsed.name)
            if url_name:
                unit_price = self._historical_or_current_market_price(url_name, traded_at)
                return TradeAnalysisItem(
                    name=external_name or parsed.name,
                    quantity=parsed.quantity,
                    unit_price=unit_price,
                    total_value=round(parsed.quantity * unit_price, 2),
                    vaulted=False,
                    matched=True,
                )
            return TradeAnalysisItem(
                name=parsed.name,
                quantity=parsed.quantity,
                unit_price=0,
                total_value=0,
                vaulted=False,
                matched=False,
            )
        unit_price = self._historical_or_current_price(item, traded_at)
        return TradeAnalysisItem(
            name=item.name,
            quantity=parsed.quantity,
            unit_price=unit_price,
            total_value=round(parsed.quantity * unit_price, 2),
            vaulted=item.vaulted,
            matched=True,
        )

    def _historical_or_current_price(self, item: Item, traded_at: datetime | None) -> float:
        url_name = self.market_url_names.get(item.name)
        if self.use_historical and url_name and traded_at:
            historical = self._historical_min_price(url_name, traded_at)
            if historical is not None:
                return historical
        price = self.prices.price_for_item(item.id)
        return float(price.current_price) if price else 0.0

    def _historical_or_current_market_price(self, url_name: str, traded_at: datetime | None) -> float:
        if self.use_historical and traded_at:
            historical = self._historical_min_price(url_name, traded_at)
            if historical is not None:
                return historical
        return self._current_market_price(url_name)

    def _current_market_price(self, url_name: str) -> float:
        if url_name in self._quote_cache:
            return self._quote_cache[url_name]
        try:
            quote = MarketPriceService._fetch_quote(url_name)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            self._quote_cache[url_name] = 0.0
            return 0.0
        self._quote_cache[url_name] = float(quote.current_price)
        return self._quote_cache[url_name]

    def _external_market_match(self, name: str) -> tuple[str | None, str | None]:
        clean_name = self._market_lookup_name(name)
        names = self._external_market_item_names()
        url_name = names.get(clean_name.lower())
        if url_name:
            return clean_name, url_name
        fallback = self._market_slug(clean_name)
        if self._market_url_exists(fallback):
            return clean_name, fallback
        return None, None

    @staticmethod
    def _market_lookup_name(name: str) -> str:
        return re.sub(r"\s*\([^)]*RANK\s+\d+[^)]*\)\s*$", "", name, flags=re.I).strip()

    @staticmethod
    def _market_slug(name: str) -> str:
        slug = name.lower().replace("&", " and ")
        return re.sub(r"[^a-z0-9]+", "_", slug).strip("_")

    def _market_url_exists(self, url_name: str) -> bool:
        return self._current_market_price(url_name) > 0 or bool(self._statistics_90_days(url_name))

    def _external_market_item_names(self) -> dict[str, str]:
        if self._external_market_names is not None:
            return self._external_market_names
        request = Request(
            "https://api.warframe.market/v1/items",
            headers={"Accept": "application/json", "Language": "en", "Platform": "pc", "User-Agent": "TradeFrame/0.1 local trade analysis"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, IncompleteRead, json.JSONDecodeError, ValueError):
            self._external_market_names = {}
            return self._external_market_names
        items = payload.get("payload", {}).get("items", [])
        names: dict[str, str] = {}
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_name = item.get("item_name")
                url_name = item.get("url_name")
                if isinstance(item_name, str) and isinstance(url_name, str):
                    names[item_name.lower()] = url_name
        self._external_market_names = names
        return names

    def _historical_min_price(self, url_name: str, traded_at: datetime) -> float | None:
        stats = self._statistics_90_days(url_name)
        if not stats:
            return None
        trade_date = traded_at.replace(tzinfo=timezone.utc) if traded_at.tzinfo is None else traded_at.astimezone(timezone.utc)
        best_price: float | None = None
        best_delta: float | None = None
        for row in stats:
            date_text = row.get("datetime")
            min_price = row.get("min_price")
            if not isinstance(date_text, str) or not isinstance(min_price, int | float):
                continue
            try:
                stat_date = datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            delta = abs((trade_date - stat_date).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_price = float(min_price)
        return best_price

    def _statistics_90_days(self, url_name: str) -> list[dict[str, object]]:
        if url_name in self._history_cache:
            return self._history_cache[url_name]
        request = Request(
            f"https://api.warframe.market/v1/items/{url_name}/statistics",
            headers={"Accept": "application/json", "Language": "en", "Platform": "pc", "User-Agent": "TradeFrame/0.1 local trade analysis"},
        )
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, IncompleteRead, json.JSONDecodeError, ValueError):
            self._history_cache[url_name] = []
            return []
        stats = payload.get("payload", {}).get("statistics_closed", {}).get("90days", [])
        result = stats if isinstance(stats, list) else []
        self._history_cache[url_name] = result
        return result

    @classmethod
    def _parse_sides(cls, trade: Trade) -> tuple[list[ParsedTradeItem], list[ParsedTradeItem]]:
        given_text = cls._clean_trade_text(trade.given_text)
        received_text = cls._clean_trade_text(trade.received_text)
        marker = re.search(r"and will receive from .*? the following:", received_text, flags=re.I | re.S)
        if marker:
            before_marker = received_text[: marker.start()]
            after_marker = received_text[marker.end() :]
            given_text = given_text or before_marker
            received_text = after_marker
        return cls._split_items(given_text), cls._split_items(received_text)

    @staticmethod
    def _clean_trade_text(value: str | None) -> str:
        text = value or ""
        text = re.sub(r"title=.*$", "", text, flags=re.I | re.S)
        text = re.sub(r"leftItem=.*$", "", text, flags=re.I | re.S)
        text = re.sub(r"[\ue000-\uf8ff]", "", text)
        text = "".join(ch for ch in text if ord(ch) < 57344 or ord(ch) > 63743)
        return text.strip()

    @classmethod
    def _split_items(cls, value: str) -> list[ParsedTradeItem]:
        result: list[ParsedTradeItem] = []
        for raw in re.split(r"[\n,]+", value):
            token = raw.strip()
            if not token:
                continue
            platinum = re.match(r"^Platinum\s*x\s*(\d+)$", token, flags=re.I)
            if platinum:
                result.append(ParsedTradeItem(name="Platinum", quantity=int(platinum.group(1)), is_platinum=True))
                continue
            quantity = 1
            quantity_match = re.search(r"\s+x\s*(\d+)$", token, flags=re.I)
            if quantity_match:
                quantity = int(quantity_match.group(1))
                token = token[: quantity_match.start()].strip()
            result.append(ParsedTradeItem(name=token, quantity=quantity))
        return result


