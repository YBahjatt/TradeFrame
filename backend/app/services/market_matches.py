from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.adapters.aleca import AlecaAdapter
from app.config import get_settings
from app.schemas.dto import MarketMatchItem, MarketMatchResponse, MarketUserMatch, TradablePartRow
from app.services.collection import CollectionService
from app.services.market import MarketPriceService
from app.services.settings import SettingsService


TRADEFRAME_SUFFIX = "via TradeFrame"
WARFRAME_MARKET_USER_AGENT = "TradeFrame/2.0 (+https://github.com/YBahjatt/TradeFrame)"
DEFAULT_MAX_MISSING_ITEMS = 0
DEFAULT_MAX_USERS = 0
DEFAULT_CACHE_KEY = (DEFAULT_MAX_MISSING_ITEMS, DEFAULT_MAX_USERS)
DEFAULT_MAX_PROFILE_CHECKS_PER_SCAN = 600
STATUS_REFRESH_LIMIT = 30
STATUS_REFRESH_INTERVAL = timedelta(minutes=10)
STATUS_STALE_AFTER = timedelta(minutes=30)


@dataclass
class MarketOrder:
    user_name: str
    user_slug: str
    item_name: str
    quantity: int
    platinum: float
    status: str | None = None
    last_seen: str | None = None
    reputation: int | None = None


class MarketMatchService:
    def __init__(self, db: Session):
        self.db = db
        settings = get_settings()
        self.adapter = AlecaAdapter(settings.aleca_data_dir)
        self.collection = CollectionService(db)
        self.tradeframe_settings = SettingsService(db).get()
        self.url_names = self.adapter.read_market_url_names()
        self._item_name_by_id: dict[str, str] | None = None

    def matches(
        self,
        max_missing_items: int = DEFAULT_MAX_MISSING_ITEMS,
        max_users: int = DEFAULT_MAX_USERS,
        delay_seconds: float = 0.6,
        progress_callback: Callable[[MarketMatchResponse], None] | None = None,
        known_user_slugs: set[str] | None = None,
        scan_filters: set[tuple[str, int]] | None = None,
    ) -> MarketMatchResponse:
        delay_seconds = max(1.0, delay_seconds)
        max_missing_items = max(0, min(500, max_missing_items))
        max_users = max(0, min(1000, max_users))
        profile_limit = max_users if max_users > 0 else DEFAULT_MAX_PROFILE_CHECKS_PER_SCAN
        missing_rows = self._ranked_missing_rows(max_missing_items, scan_filters)
        tradable_rows = self.collection.tradable_parts("tradable", None)
        tradable_by_url = self._rows_by_url(tradable_rows)
        errors: list[str] = []
        sellers_by_user: dict[str, list[MarketOrder]] = defaultdict(list)
        matched_buys_by_user: dict[str, list[MarketMatchItem]] = {}
        user_info_by_slug: dict[str, MarketOrder] = {}
        checked_users = 0
        missing_checked = 0
        deferred_orders: list[MarketOrder] = []
        known_user_slugs = known_user_slugs or set()

        def check_seller(order: MarketOrder) -> bool:
            nonlocal checked_users
            sellers_by_user[order.user_slug].append(order)
            user_info_by_slug.setdefault(order.user_slug, order)
            if order.user_slug in known_user_slugs:
                return False
            if order.user_slug in matched_buys_by_user or checked_users >= profile_limit:
                return False
            checked_users += 1
            try:
                buy_orders = self._profile_buy_orders(order.user_slug)
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                errors.append(self._user_error(order.user_slug, order.user_name, exc))
                matched_buys_by_user[order.user_slug] = []
                return True
            matched_buys_by_user[order.user_slug] = self._matched_buy_items(buy_orders, tradable_by_url)
            return True

        for row in missing_rows:
            missing_checked += 1
            url_name = self._url_name_for(row.name)
            if not url_name:
                continue
            try:
                orders = sorted(
                    self._item_orders(url_name, "sell"),
                    key=lambda item: (self._status_rank(item.status), item.platinum, item.user_name.lower()),
                )
                for order in orders:
                    order.item_name = row.name
                    if self._status_rank(order.status) > 1:
                        deferred_orders.append(order)
                        continue
                    if check_seller(order):
                        self._publish_progress(progress_callback, sellers_by_user, matched_buys_by_user, user_info_by_slug, missing_rows, missing_checked, checked_users, errors)
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{row.name}: {exc}")
            self._publish_progress(progress_callback, sellers_by_user, matched_buys_by_user, user_info_by_slug, missing_rows, missing_checked, checked_users, errors)
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        for order in deferred_orders:
            if checked_users >= profile_limit:
                break
            if check_seller(order):
                self._publish_progress(progress_callback, sellers_by_user, matched_buys_by_user, user_info_by_slug, missing_rows, missing_checked, checked_users, errors)
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

        return self._build_response(
            sellers_by_user=sellers_by_user,
            matched_buys_by_user=matched_buys_by_user,
            user_info_by_slug=user_info_by_slug,
            missing_rows=missing_rows,
            missing_checked=missing_checked,
            checked_users=checked_users,
            errors=errors,
            refreshing=False,
        )

    def _matched_buy_items(
        self,
        buy_orders: list[MarketOrder],
        tradable_by_url: dict[str, list[TradablePartRow]],
    ) -> list[MarketMatchItem]:
        matched_buys: list[MarketMatchItem] = []
        for order in buy_orders:
            rows = tradable_by_url.get(self._url_name_for(order.item_name), [])
            if not rows:
                continue
            row = rows[0]
            matched_buys.append(
                MarketMatchItem(
                    name=row.name,
                    chat_text=row.chat_text,
                    quantity=min(row.quantity, order.quantity),
                    market_value=row.market_value,
                    platinum=order.platinum,
                )
            )
        return self._unique_items(matched_buys)

    def _publish_progress(
        self,
        progress_callback: Callable[[MarketMatchResponse], None] | None,
        sellers_by_user: dict[str, list[MarketOrder]],
        matched_buys_by_user: dict[str, list[MarketMatchItem]],
        user_info_by_slug: dict[str, MarketOrder],
        missing_rows: list[TradablePartRow],
        missing_checked: int,
        checked_users: int,
        errors: list[str],
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            self._build_response(
                sellers_by_user=sellers_by_user,
                matched_buys_by_user=matched_buys_by_user,
                user_info_by_slug=user_info_by_slug,
                missing_rows=missing_rows,
                missing_checked=missing_checked,
                checked_users=checked_users,
                errors=errors,
                refreshing=True,
            )
        )

    def _build_response(
        self,
        sellers_by_user: dict[str, list[MarketOrder]],
        matched_buys_by_user: dict[str, list[MarketMatchItem]],
        user_info_by_slug: dict[str, MarketOrder],
        missing_rows: list[TradablePartRow],
        missing_checked: int,
        checked_users: int,
        errors: list[str],
        refreshing: bool,
    ) -> MarketMatchResponse:
        matches: list[MarketUserMatch] = []
        for user_slug, sell_orders in sellers_by_user.items():
            matched_buys = matched_buys_by_user.get(user_slug, [])
            if not matched_buys:
                continue
            matched_sells = self._unique_items([
                MarketMatchItem(
                    name=order.item_name,
                    chat_text=CollectionService._chat_link(order.item_name),
                    quantity=order.quantity,
                    market_value=self._market_value_for_missing(order.item_name, missing_rows),
                    platinum=order.platinum,
                )
                for order in sell_orders
            ])
            if not matched_sells:
                continue
            user_info = user_info_by_slug.get(user_slug, sell_orders[0])
            matches.append(
                MarketUserMatch(
                    user_name=user_info.user_name,
                    user_slug=user_slug,
                    status=user_info.status,
                    last_seen=user_info.last_seen,
                    reputation=user_info.reputation,
                    they_sell=sorted(matched_sells, key=lambda item: (-item.market_value, item.name)),
                    they_buy=sorted(matched_buys, key=lambda item: (item.market_value, item.name)),
                    copy_texts=self._copy_texts(user_info.user_name, matched_buys, matched_sells),
                )
            )
        matches = self._sort_matches(matches)
        missing_part_quantity_total = sum(row.quantity for row in missing_rows)
        missing_part_quantity_checked = sum(row.quantity for row in missing_rows[:missing_checked])
        return MarketMatchResponse(
            matches=matches,
            missing_items_checked=missing_checked,
            missing_part_quantity_checked=missing_part_quantity_checked,
            missing_part_types_total=len(missing_rows),
            missing_part_quantity_total=missing_part_quantity_total,
            users_checked=checked_users,
            errors=errors[:20],
            generated_at=datetime.now(timezone.utc).isoformat(),
            refreshing=refreshing,
        )

    def refresh_match_statuses(self, response: MarketMatchResponse) -> MarketMatchResponse:
        orders_by_item: dict[str, list[MarketOrder]] = {}
        updated_matches: list[MarketUserMatch] = []
        errors = list(response.errors)
        for match in response.matches[:STATUS_REFRESH_LIMIT]:
            status_order: MarketOrder | None = None
            for item in match.they_sell:
                url_name = self._url_name_for(item.name)
                if not url_name:
                    continue
                try:
                    orders = orders_by_item.get(url_name)
                    if orders is None:
                        orders = self._item_orders(url_name, "sell")
                        orders_by_item[url_name] = orders
                    status_order = next((order for order in orders if order.user_slug == match.user_slug), None)
                except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(self._user_error(match.user_slug, match.user_name, exc))
                    status_order = None
                if status_order is not None:
                    break
            if status_order is None:
                updated_matches.append(match)
                continue
            updated_matches.append(
                match.model_copy(
                    update={
                        "user_name": status_order.user_name or match.user_name,
                        "status": status_order.status,
                        "last_seen": status_order.last_seen,
                        "reputation": status_order.reputation,
                    }
                )
            )
            time.sleep(0.35)
        if len(response.matches) > STATUS_REFRESH_LIMIT:
            updated_matches.extend(response.matches[STATUS_REFRESH_LIMIT:])
        return response.model_copy(update={"matches": self._sort_matches(updated_matches), "errors": errors[:20]})

    def _ranked_missing_rows(self, max_missing_items: int, scan_filters: set[tuple[str, int]] | None = None) -> list[TradablePartRow]:
        rows = self.collection.tradable_parts("missing", None)
        if scan_filters:
            missing_tags = self._missing_lead_tags()
            rows = [row for row in rows if missing_tags.get(row.name, set()) & scan_filters]
        ranked = sorted(rows, key=lambda row: (-row.market_value, row.name))
        if max_missing_items <= 0:
            return ranked
        return ranked[:max_missing_items]

    def _rows_by_url(self, rows: list[TradablePartRow]) -> dict[str, list[TradablePartRow]]:
        result: dict[str, list[TradablePartRow]] = defaultdict(list)
        for row in rows:
            url_name = self._url_name_for(row.name)
            if url_name:
                result[url_name].append(row)
        for bucket in result.values():
            bucket.sort(key=lambda row: (row.market_value, row.name))
        return result

    def _url_name_for(self, item_name: str) -> str | None:
        if item_name in self.url_names:
            return self.url_names[item_name]
        if item_name.endswith(" Prime"):
            return MarketPriceService._set_url_name(item_name)
        slug = item_name.lower().replace("&", " and ")
        return re.sub(r"[^a-z0-9]+", "_", slug).strip("_") or None

    @staticmethod
    def _status_rank(status: str | None) -> int:
        return {"ingame": 0, "online": 1, "offline": 3, "invisible": 4}.get((status or "").lower(), 2)

    @staticmethod
    def _fresh_status(status: str | None, last_seen: str | None, now: datetime | None = None) -> str | None:
        normalized = (status or "").lower() or None
        if normalized not in {"ingame", "online"} or not last_seen:
            return normalized
        try:
            seen_at = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        except ValueError:
            return normalized
        if seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current - seen_at > STATUS_STALE_AFTER:
            return "offline"
        return normalized

    @staticmethod
    def _trade_fit_score(match: MarketUserMatch) -> float:
        status_bonus = {"ingame": 1000.0, "online": 850.0, "offline": 0.0, "invisible": -100.0}.get((match.status or "").lower(), 250.0)
        sell_count = len(match.they_sell)
        buy_count = len(match.they_buy)
        two_way_count = min(sell_count, buy_count)
        they_sell_value = sum((item.platinum or item.market_value) for item in match.they_sell)
        they_buy_value = sum((item.platinum or item.market_value) for item in match.they_buy)
        larger_value = max(they_sell_value, they_buy_value, 1.0)
        value_fit = min(they_sell_value, they_buy_value) / larger_value
        useful_value = min(they_sell_value, they_buy_value)
        reputation_bonus = min(max(match.reputation or 0, 0), 100) * 0.5
        return (
            status_bonus
            + two_way_count * 120.0
            + sell_count * 35.0
            + buy_count * 45.0
            + value_fit * 250.0
            + useful_value * 1.5
            + reputation_bonus
        )

    @staticmethod
    def _with_trade_fit_score(match: MarketUserMatch) -> MarketUserMatch:
        score = round(MarketMatchService._trade_fit_score(match), 2)
        if match.trade_fit_score == score:
            return match
        return match.model_copy(update={"trade_fit_score": score})

    @staticmethod
    def _sort_matches(matches: list[MarketUserMatch]) -> list[MarketUserMatch]:
        scored = [MarketMatchService._with_trade_fit_score(MarketMatchService._with_fresh_status(match)) for match in matches]
        scored.sort(key=lambda match: (MarketMatchService._status_rank(match.status), -match.trade_fit_score, match.user_name.lower()))
        return scored

    @staticmethod
    def _with_fresh_status(match: MarketUserMatch) -> MarketUserMatch:
        status = MarketMatchService._fresh_status(match.status, match.last_seen)
        if status == match.status:
            return match
        return match.model_copy(update={"status": status})

    @staticmethod
    def _unique_items(items: list[MarketMatchItem]) -> list[MarketMatchItem]:
        by_name: dict[str, MarketMatchItem] = {}
        for item in items:
            current = by_name.get(item.name)
            if current is None:
                by_name[item.name] = item
            else:
                current.quantity = max(current.quantity, item.quantity)
                current.platinum = min(current.platinum or item.platinum, item.platinum)
        return list(by_name.values())

    @staticmethod
    def _market_value_for_missing(name: str, missing_rows: list[TradablePartRow]) -> float:
        for row in missing_rows:
            if row.name == name:
                return row.market_value
        return 0

    def _copy_texts(self, user_name: str, mine: list[MarketMatchItem], theirs: list[MarketMatchItem]) -> list[str]:
        max_length = max(50, self.tradeframe_settings.warframe_chat_max_length - self.tradeframe_settings.warframe_chat_margin)
        mine_sorted = sorted(mine, key=lambda item: (item.market_value, item.name))
        theirs_sorted = sorted(theirs, key=lambda item: (-item.market_value, item.name))
        one_message = self._message(user_name, mine_sorted, theirs_sorted)
        if len(one_message) <= max_length:
            return [one_message]

        return [
            self._intro_message(user_name, max_length),
            self._parts_message("Parts I think you want ", mine_sorted, max_length, cheapest_first=True),
            self._parts_message("Parts I want ", theirs_sorted, max_length, cheapest_first=False),
        ]

    def _fit_items(
        self,
        user_name: str,
        items: list[MarketMatchItem],
        start: int,
        existing: list[MarketMatchItem],
        max_length: int,
        side: str,
    ) -> tuple[list[MarketMatchItem], int]:
        result: list[MarketMatchItem] = []
        index = start
        while index < len(items):
            candidate = result + [items[index]]
            mine = candidate if side == "mine" else existing
            theirs = existing if side == "mine" else candidate
            if mine and theirs and len(self._message(user_name, mine, theirs)) > max_length:
                break
            result = candidate
            index += 1
        if not result and start < len(items):
            return [items[start]], start + 1
        return result, index

    @staticmethod
    def _message(user_name: str, mine: list[MarketMatchItem], theirs: list[MarketMatchItem]) -> str:
        mine_text = "".join(MarketMatchService._compact_chat_text(item.chat_text) for item in mine)
        their_text = "".join(MarketMatchService._compact_chat_text(item.chat_text) for item in theirs)
        return f"/w {user_name} WTT have {mine_text} need {their_text} {TRADEFRAME_SUFFIX}"

    @staticmethod
    def _intro_message(user_name: str, max_length: int) -> str:
        message = f"/w {user_name} I want to trade parts with you"
        if len(message) <= max_length:
            return message
        return f"/w {user_name} WTT"

    @staticmethod
    def _parts_message(prefix: str, items: list[MarketMatchItem], max_length: int, cheapest_first: bool) -> str:
        sorted_items = sorted(items, key=lambda item: ((item.market_value, item.name) if cheapest_first else (-item.market_value, item.name)))
        selected: list[MarketMatchItem] = []
        for item in sorted_items:
            candidate = selected + [item]
            if len(prefix + "".join(MarketMatchService._compact_chat_text(part.chat_text) for part in candidate)) > max_length:
                continue
            selected = candidate
        if selected:
            return prefix + "".join(MarketMatchService._compact_chat_text(item.chat_text) for item in selected)
        return prefix + (MarketMatchService._compact_chat_text(sorted_items[0].chat_text) if sorted_items else "")

    @staticmethod
    def _compact_chat_text(text: str) -> str:
        return text.replace("] BP", "]BP")

    @staticmethod
    def _user_error(user_slug: str, user_name: str, exc: Exception) -> str:
        return f"user:{user_slug}|{user_name}: {exc}"

    def sync_with_inventory(self, response: MarketMatchResponse) -> MarketMatchResponse:
        missing_rows = {row.name: row for row in self.collection.tradable_parts("missing", None)}
        tradable_rows = {row.name: row for row in self.collection.tradable_parts("tradable", None)}
        missing_filter_tags = self._missing_lead_tags()
        synced_matches: list[MarketUserMatch] = []
        for match in response.matches:
            they_sell: list[MarketMatchItem] = []
            for item in match.they_sell:
                current = missing_rows.get(item.name)
                if current is None:
                    continue
                lead_tags = self._lead_tag_strings(missing_filter_tags.get(item.name, set()))
                they_sell.append(
                    item.model_copy(
                        update={
                            "chat_text": current.chat_text,
                            "quantity": min(item.quantity, current.quantity),
                            "market_value": current.market_value,
                            "lead_tags": lead_tags,
                        }
                    )
                )
            they_buy: list[MarketMatchItem] = []
            for item in match.they_buy:
                current = tradable_rows.get(item.name)
                if current is None:
                    continue
                they_buy.append(
                    item.model_copy(
                        update={
                            "chat_text": current.chat_text,
                            "quantity": min(item.quantity, current.quantity),
                            "market_value": current.market_value,
                            "lead_tags": [],
                        }
                    )
                )
            if not they_sell or not they_buy:
                continue
            synced_matches.append(
                match.model_copy(
                    update={
                        "they_sell": sorted(self._unique_items(they_sell), key=lambda item: (-item.market_value, item.name)),
                        "they_buy": sorted(self._unique_items(they_buy), key=lambda item: (item.market_value, item.name)),
                        "copy_texts": self._copy_texts(match.user_name, they_buy, they_sell),
                    }
                )
            )
        return response.model_copy(update={"matches": self._sort_matches(synced_matches)})

    @staticmethod
    def _lead_tag_strings(tags: set[tuple[str, int]]) -> list[str]:
        return [f"{row_key}:{bucket}" for row_key, bucket in sorted(tags)]

    def _missing_lead_tags(self) -> dict[str, set[tuple[str, int]]]:
        rows = self.collection.inventory_rows()
        groups = self.collection._prime_item_groups(rows)
        tags: dict[str, set[tuple[str, int]]] = defaultdict(set)
        for group in groups.values():
            if not self.collection._has_set_parts(group):
                continue
            row_key = "not" if not bool(group["built"] or group["mastered"]) else "owned_mastered"
            parts = self.collection._effective_set_math_parts(group, groups)
            if row_key == "not":
                _, partial_sets = self.collection._first_set_details(parts)
            else:
                _, partial_sets = self.collection._set_multiplicity_details(parts)
                partial_sets = self.collection._actionable_partial_sets(parts, partial_sets)
            for missing in partial_sets:
                bucket = self.collection._missing_bucket(sum(missing.values()))
                for part_name in missing:
                    tags[part_name].add((row_key, bucket))
        return tags

    @staticmethod
    def _item_orders(url_name: str, order_type: str) -> list[MarketOrder]:
        payload = MarketMatchService._get_json(f"https://api.warframe.market/v2/orders/item/{url_name}")
        orders = payload.get("data", [])
        result: list[MarketOrder] = []
        for order in orders if isinstance(orders, list) else []:
            if order.get("type") != order_type or not order.get("visible", True):
                continue
            user = order.get("user") if isinstance(order.get("user"), dict) else {}
            user_name = str(user.get("ingameName") or "").strip()
            user_slug = str(user.get("slug") or user_name.lower()).strip()
            if not user_name:
                continue
            result.append(
                MarketOrder(
                    user_name=user_name,
                    user_slug=user_slug,
                    item_name="",
                    quantity=int(order.get("quantity") or 1),
                    platinum=float(order.get("platinum") or 0),
                    status=MarketMatchService._fresh_status(user.get("status"), user.get("lastSeen") or user.get("lastSeenAt")),
                    last_seen=user.get("lastSeen") or user.get("lastSeenAt"),
                    reputation=user.get("reputation"),
                )
            )
        return result

    def _profile_buy_orders(self, user_slug: str) -> list[MarketOrder]:
        payload = MarketMatchService._get_json(f"https://api.warframe.market/v2/orders/user/{user_slug}")
        orders = payload.get("data", [])
        item_names = self._v2_item_name_by_id()
        result: list[MarketOrder] = []
        for order in orders:
            if order.get("type") != "buy" or not order.get("visible", True):
                continue
            item_name = item_names.get(str(order.get("itemId") or ""))
            if not item_name:
                continue
            result.append(
                MarketOrder(
                    user_name=user_slug,
                    user_slug=user_slug,
                    item_name=str(item_name),
                    quantity=int(order.get("quantity") or 1),
                    platinum=float(order.get("platinum") or 0),
                )
            )
        return result

    def _v2_item_name_by_id(self) -> dict[str, str]:
        if self._item_name_by_id is not None:
            return self._item_name_by_id
        payload = MarketMatchService._get_json("https://api.warframe.market/v2/items")
        rows = payload.get("data", [])
        result: dict[str, str] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id") or "")
            i18n = row.get("i18n") if isinstance(row.get("i18n"), dict) else {}
            en = i18n.get("en") if isinstance(i18n.get("en"), dict) else {}
            name = en.get("name")
            if item_id and isinstance(name, str):
                result[item_id] = name
        self._item_name_by_id = result
        return result

    @staticmethod
    def _get_json(url: str) -> dict[str, object]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Language": "en",
                "Platform": "pc",
                "User-Agent": WARFRAME_MARKET_USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 429:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                wait_seconds = max(1.0, min(10.0, float(retry_after or "1")))
            except ValueError:
                wait_seconds = 1.0
            time.sleep(wait_seconds)
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))


class MarketMatchCache:
    def __init__(self, refresh_interval_minutes: int = 15):
        self.refresh_interval = timedelta(minutes=refresh_interval_minutes)
        self.cache_path = Path(__file__).resolve().parents[3] / "data" / "market_matches_cache.json"
        self._lock = threading.Lock()
        self._results: dict[tuple[int, int], MarketMatchResponse] = {}
        self._refreshing: set[tuple[int, int]] = set()
        self._status_refreshing: set[tuple[int, int]] = set()
        self._last_status_refresh: dict[tuple[int, int], datetime] = {}
        self._scan_filters: dict[tuple[int, int], set[tuple[str, int]]] = {}
        self._background_started = False
        self._load_from_disk()

    def get(
        self,
        max_missing_items: int = DEFAULT_MAX_MISSING_ITEMS,
        max_users: int = DEFAULT_MAX_USERS,
        refresh: bool = False,
        scan_filters: set[tuple[str, int]] | None = None,
        status_refresh: bool = False,
    ) -> MarketMatchResponse:
        key = (max(0, min(500, max_missing_items)), max(0, min(1000, max_users)))
        with self._lock:
            if scan_filters is not None:
                self._scan_filters[key] = scan_filters
                self._save_to_disk_locked()
            active_scan_filters = self._scan_filters.get(key, set())
            current = self._results.get(key)
            should_refresh = refresh or current is None or self._is_stale(current)
            if should_refresh:
                self._start_refresh_locked(key, active_scan_filters)
            if current is not None:
                current = self._normalize_counters(current)
                self._results[key] = current
                if status_refresh:
                    self._status_refreshing.add(key)
                else:
                    self._maybe_start_status_refresh_locked(key, current)
                snapshot = current.model_copy(
                    update={
                        "refreshing": key in self._refreshing or key in self._status_refreshing,
                        **self._scan_scope_update(active_scan_filters),
                    }
                )
            else:
                return MarketMatchResponse(
                    matches=[],
                    missing_items_checked=0,
                    users_checked=0,
                    errors=[],
                    generated_at=None,
                    refreshing=True,
                    **self._scan_scope_update(active_scan_filters),
                )
        from app.database.session import SessionLocal

        with SessionLocal() as db:
            if status_refresh and snapshot.matches:
                try:
                    refreshed = MarketMatchService(db).refresh_match_statuses(snapshot)
                    with self._lock:
                        current = self._results.get(key)
                        self._results[key] = self._merge_results(current, refreshed).model_copy(update={"refreshing": key in self._refreshing})
                        self._last_status_refresh[key] = datetime.now(timezone.utc)
                        self._save_to_disk_locked()
                        snapshot = self._results[key].model_copy(update={**self._scan_scope_update(active_scan_filters)})
                finally:
                    with self._lock:
                        self._status_refreshing.discard(key)
            return MarketMatchService(db).sync_with_inventory(snapshot)

    def warm_default(self) -> None:
        with self._lock:
            self._start_refresh_locked(DEFAULT_CACHE_KEY, self._scan_filters.get(DEFAULT_CACHE_KEY, set()))

    def start_background_refresh(self) -> None:
        with self._lock:
            if self._background_started:
                return
            self._background_started = True
            self._start_refresh_locked(DEFAULT_CACHE_KEY, self._scan_filters.get(DEFAULT_CACHE_KEY, set()))
        thread = threading.Thread(target=self._background_loop, daemon=True)
        thread.start()

    def _background_loop(self) -> None:
        while True:
            time.sleep(self.refresh_interval.total_seconds())
            with self._lock:
                self._start_refresh_locked(DEFAULT_CACHE_KEY, self._scan_filters.get(DEFAULT_CACHE_KEY, set()))

    def _start_refresh_locked(self, key: tuple[int, int], scan_filters: set[tuple[str, int]] | None = None) -> None:
        if key in self._refreshing:
            return
        self._refreshing.add(key)
        thread = threading.Thread(target=self._refresh, args=(key[0], key[1], set(scan_filters or set())), daemon=True)
        thread.start()

    def _maybe_start_status_refresh_locked(self, key: tuple[int, int], result: MarketMatchResponse) -> None:
        if not result.matches or key in self._status_refreshing:
            return
        last_refresh = self._last_status_refresh.get(key)
        if last_refresh is not None and datetime.now(timezone.utc) - last_refresh < STATUS_REFRESH_INTERVAL:
            return
        self._status_refreshing.add(key)
        thread = threading.Thread(target=self._refresh_statuses, args=(key, result), daemon=True)
        thread.start()

    def _refresh(self, max_missing_items: int, max_users: int, scan_filters: set[tuple[str, int]]) -> None:
        from app.database.session import SessionLocal

        key = (max_missing_items, max_users)
        try:
            with self._lock:
                current = self._results.get(key)
                known_user_slugs = {match.user_slug for match in current.matches} if current is not None else set()
            with SessionLocal() as db:
                result = MarketMatchService(db).matches(
                    max_missing_items=max_missing_items,
                    max_users=max_users,
                    progress_callback=lambda partial: self._store_progress(key, partial),
                    known_user_slugs=known_user_slugs,
                    scan_filters=scan_filters,
                )
            with self._lock:
                current = self._results.get(key)
                self._results[key] = self._merge_results(current, result).model_copy(update={"refreshing": False})
                self._save_to_disk_locked()
        except Exception as exc:
            with self._lock:
                current = self._results.get(key)
                errors = [str(exc)]
                if current is not None:
                    self._results[key] = current.model_copy(update={"errors": errors, "refreshing": False})
                else:
                    self._results[key] = MarketMatchResponse(
                        matches=[],
                        missing_items_checked=0,
                        users_checked=0,
                        errors=errors,
                        generated_at=datetime.now(timezone.utc).isoformat(),
                        refreshing=False,
                    )
                self._save_to_disk_locked()
        finally:
            with self._lock:
                self._refreshing.discard(key)

    def _refresh_statuses(self, key: tuple[int, int], result: MarketMatchResponse) -> None:
        try:
            refreshed = self._refresh_visible_statuses(result)
            with self._lock:
                current = self._results.get(key)
                self._results[key] = self._merge_results(current, refreshed).model_copy(update={"refreshing": key in self._refreshing})
                self._last_status_refresh[key] = datetime.now(timezone.utc)
                self._save_to_disk_locked()
        finally:
            with self._lock:
                self._status_refreshing.discard(key)

    def _store_progress(self, key: tuple[int, int], result: MarketMatchResponse) -> None:
        with self._lock:
            self._results[key] = self._merge_results(self._results.get(key), result).model_copy(update={"refreshing": True})
            self._save_to_disk_locked()

    def _refresh_visible_statuses(self, result: MarketMatchResponse) -> MarketMatchResponse:
        from app.database.session import SessionLocal

        try:
            with SessionLocal() as db:
                return MarketMatchService(db).refresh_match_statuses(result)
        except Exception as exc:
            errors = [str(exc), *result.errors]
            return result.model_copy(update={"errors": errors[:20]})

    def _merge_results(self, current: MarketMatchResponse | None, incoming: MarketMatchResponse) -> MarketMatchResponse:
        if current is None:
            return incoming
        by_slug = {match.user_slug: match for match in current.matches}
        for match in incoming.matches:
            by_slug[match.user_slug] = match
        matches = MarketMatchService._sort_matches(list(by_slug.values()))
        incoming_success_slugs = {match.user_slug for match in incoming.matches}
        incoming_errors = [MarketMatchCache._normalize_error(error) for error in incoming.errors]
        current_errors = [
            MarketMatchCache._normalize_error(error)
            for error in current.errors
            if MarketMatchCache._error_user_slug(error) not in incoming_success_slugs
        ]
        errors = [error for error in [*incoming_errors, *[error for error in current_errors if error not in incoming_errors]] if error][:20]
        missing_items_checked = max(current.missing_items_checked, incoming.missing_items_checked)
        missing_part_types_total = max(current.missing_part_types_total, incoming.missing_part_types_total)
        missing_part_quantity_total = max(current.missing_part_quantity_total, incoming.missing_part_quantity_total)
        missing_part_quantity_checked = max(current.missing_part_quantity_checked, incoming.missing_part_quantity_checked)
        if missing_part_types_total > 0 and missing_items_checked >= missing_part_types_total:
            missing_part_quantity_checked = missing_part_quantity_total
        return incoming.model_copy(
            update={
                "matches": matches,
                "missing_items_checked": missing_items_checked,
                "missing_part_quantity_checked": missing_part_quantity_checked,
                "missing_part_types_total": missing_part_types_total,
                "missing_part_quantity_total": missing_part_quantity_total,
                "users_checked": max(current.users_checked, incoming.users_checked),
                "errors": errors,
                "generated_at": incoming.generated_at or current.generated_at,
                "refreshing": incoming.refreshing,
            }
        )

    @staticmethod
    def _error_user_slug(error: str) -> str | None:
        if not error.startswith("user:") or "|" not in error:
            return None
        return error[5:error.index("|")]

    @staticmethod
    def _normalize_error(error: str) -> str:
        if "type object 'MarketMatchService'" in error:
            return ""
        if error.startswith("user:") and "|" in error:
            return error.split("|", 1)[1]
        return error

    @staticmethod
    def _normalize_counters(result: MarketMatchResponse) -> MarketMatchResponse:
        updates: dict[str, object] = {}
        if result.missing_part_types_total > 0 and result.missing_items_checked >= result.missing_part_types_total:
            if result.missing_part_quantity_total > result.missing_part_quantity_checked:
                updates["missing_part_quantity_checked"] = result.missing_part_quantity_total
        sorted_matches = MarketMatchService._sort_matches(result.matches)
        if sorted_matches != result.matches:
            updates["matches"] = sorted_matches
        normalized_errors = MarketMatchCache._prune_resolved_errors(result.errors, sorted_matches)
        if normalized_errors != result.errors:
            updates["errors"] = normalized_errors
        if updates:
            return result.model_copy(update=updates)
        return result

    @staticmethod
    def _prune_resolved_errors(errors: list[str], matches: list[MarketUserMatch]) -> list[str]:
        successful_users = {match.user_name.lower() for match in matches}
        successful_slugs = {match.user_slug.lower() for match in matches}
        result: list[str] = []
        for error in errors:
            slug = MarketMatchCache._error_user_slug(error)
            visible = MarketMatchCache._normalize_error(error)
            if not visible:
                continue
            name = visible.split(":", 1)[0].strip().lower() if ":" in visible else ""
            if slug is not None and slug.lower() in successful_slugs:
                continue
            if "HTTP Error 429" in visible and name in successful_users:
                continue
            if visible not in result:
                result.append(visible)
        return result[:20]

    @staticmethod
    def _scan_scope_update(scan_filters: set[tuple[str, int]]) -> dict[str, list[int]]:
        return {
            "scan_owned_missing": sorted(bucket for row_key, bucket in scan_filters if row_key == "owned_mastered"),
            "scan_not_missing": sorted(bucket for row_key, bucket in scan_filters if row_key == "not"),
        }

    def _load_from_disk(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            values = raw.get("results") if isinstance(raw.get("results"), dict) else raw
            scan_filters = raw.get("scan_filters") if isinstance(raw.get("scan_filters"), dict) else {}
            for key_text, value in values.items():
                left, right = key_text.split(",", 1)
                key = (int(left), int(right))
                self._results[key] = MarketMatchResponse.model_validate(value).model_copy(update={"refreshing": False})
            for key_text, values in scan_filters.items():
                left, right = key_text.split(",", 1)
                if isinstance(values, list):
                    self._scan_filters[(int(left), int(right))] = self._scan_filters_from_strings(values)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._results = {}

    def _save_to_disk_locked(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                f"{key[0]},{key[1]}": result.model_copy(update={"refreshing": False}).model_dump(mode="json")
                for key, result in self._results.items()
            }
            scan_payload = {
                f"{key[0]},{key[1]}": self._scan_filter_strings(value)
                for key, value in self._scan_filters.items()
            }
            self.cache_path.write_text(json.dumps({"results": payload, "scan_filters": scan_payload}, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _scan_filter_strings(scan_filters: set[tuple[str, int]]) -> list[str]:
        return [f"{row_key}:{bucket}" for row_key, bucket in sorted(scan_filters)]

    @staticmethod
    def _scan_filters_from_strings(values: list[object]) -> set[tuple[str, int]]:
        result: set[tuple[str, int]] = set()
        for value in values:
            if not isinstance(value, str) or ":" not in value:
                continue
            row_key, raw_bucket = value.split(":", 1)
            try:
                bucket = int(raw_bucket)
            except ValueError:
                continue
            if row_key in {"owned_mastered", "not"} and bucket in {1, 2, 3, 4}:
                result.add((row_key, bucket))
        return result

    @staticmethod
    def _is_stale(result: MarketMatchResponse) -> bool:
        if not result.generated_at:
            return True
        try:
            generated = datetime.fromisoformat(result.generated_at)
        except ValueError:
            return True
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - generated > timedelta(minutes=15)


market_match_cache = MarketMatchCache()
