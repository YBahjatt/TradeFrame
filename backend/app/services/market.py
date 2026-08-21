import json
import re
import statistics
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.aleca import AlecaAdapter
from app.models.entities import Item
from app.repositories.base import PriceRepository
from app.schemas.dto import MarketImportResult


@dataclass(frozen=True)
class MarketQuote:
    current_price: float
    average_price: float


class MarketPriceService:
    def __init__(self, db: Session, adapter: AlecaAdapter):
        self.db = db
        self.adapter = adapter
        self.prices = PriceRepository(db)

    def import_prices(self, delay_seconds: float = 0.12, limit: int | None = None) -> MarketImportResult:
        url_names = self.adapter.read_market_url_names()
        all_prime_items = list(self.db.scalars(select(Item).where(Item.name.contains(" Prime")).order_by(Item.name)))
        for item in all_prime_items:
            if item.name not in url_names and item.name.endswith(" Prime"):
                url_names[item.name] = self._set_url_name(item.name)
        items = [item for item in all_prime_items if item.name in url_names]
        if limit is not None:
            items = items[:limit]

        fetched = 0
        updated = 0
        skipped = 0
        failed = 0
        seen_urls: set[str] = set()
        quote_by_url: dict[str, MarketQuote] = {}

        for item in items:
            url_name = url_names.get(item.name)
            if not url_name:
                skipped += 1
                continue
            try:
                if url_name not in quote_by_url:
                    quote_by_url[url_name] = self._fetch_quote(url_name)
                    fetched += 1
                    seen_urls.add(url_name)
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                quote = quote_by_url[url_name]
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                failed += 1
                continue
            self.prices.upsert_price(item.id, quote.current_price, quote.average_price)
            updated += 1
            if updated % 50 == 0:
                self.db.commit()

        self.db.commit()
        return MarketImportResult(
            status="success" if failed == 0 else "partial",
            message=f"Imported Warframe Market prices for {updated} items from {fetched} market URLs.",
            fetched=fetched,
            updated=updated,
            skipped=skipped,
            failed=failed,
        )

    @staticmethod
    def _set_url_name(name: str) -> str:
        slug = name.lower().replace("&", " and ")
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        return f"{slug}_set"

    @staticmethod
    def _fetch_quote(url_name: str) -> MarketQuote:
        url = f"https://api.warframe.market/v2/orders/item/{url_name}/top"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Language": "en",
                "Platform": "pc",
                "User-Agent": "TradeFrame/0.1 local price importer",
            },
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        orders = payload.get("data", {}).get("sell", [])
        sell_prices = sorted(
            float(order["platinum"])
            for order in orders
            if order.get("type") == "sell"
            and order.get("visible", True)
            and isinstance(order.get("platinum"), int | float)
        )
        if not sell_prices:
            raise ValueError(f"No sell orders found for {url_name}")
        return MarketQuote(current_price=sell_prices[0], average_price=float(statistics.median(sell_prices[:5])))
