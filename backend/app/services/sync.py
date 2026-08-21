import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.aleca import AlecaAdapter
from app.models.entities import Inventory, Item, MarketPrice, PortfolioPartLock, SyncRun, Trade
from app.repositories.base import InventoryRepository, ItemRepository, TradeRepository
from app.schemas.dto import SyncResult


class SyncService:
    def __init__(self, db: Session, adapter: AlecaAdapter):
        self.db = db
        self.adapter = adapter
        self.items = ItemRepository(db)
        self.inventory = InventoryRepository(db)
        self.trades = TradeRepository(db)

    def sync(self) -> SyncResult:
        run = SyncRun(status="running")
        self.db.add(run)
        self.db.flush()
        try:
            reference_items = self.adapter.read_reference_items()
            reference_unique_names = {ref["unique_name"] for ref in reference_items}
            obsolete_ids = list(self.db.scalars(select(Item.id).where(Item.unique_name.not_in(reference_unique_names))))
            if obsolete_ids:
                self.db.query(PortfolioPartLock).filter(PortfolioPartLock.item_id.in_(obsolete_ids)).update(
                    {PortfolioPartLock.item_id: None},
                    synchronize_session=False,
                )
                self.db.query(MarketPrice).filter(MarketPrice.item_id.in_(obsolete_ids)).delete(synchronize_session=False)
                self.db.query(Inventory).filter(Inventory.item_id.in_(obsolete_ids)).delete(synchronize_session=False)
                self.db.query(Item).filter(Item.id.in_(obsolete_ids)).delete(synchronize_session=False)
                self.db.flush()
            for ref in reference_items:
                self.items.upsert(Item(**ref))
            self.db.flush()

            inventory_payload = self.adapter.read_inventory()
            counts, mastered = self._extract_inventory_facts(inventory_payload)
            pending_recipes = self._extract_pending_recipe_types(inventory_payload)
            known_items = self.items.all_prime_parts()
            blueprint_by_parent = {item.name[:-10]: item.unique_name for item in known_items if item.name.endswith(" Blueprint")}
            matched_counts = sum(1 for item in known_items if counts.get(item.unique_name, counts.get(item.name, 0)) > 0)
            if not counts or matched_counts == 0:
                raise RuntimeError("AlecaFrame inventory extraction returned no matching owned items; refusing to overwrite TradeFrame inventory.")
            for item in known_items:
                direct_owned = self._inventory_count_for_item(item.unique_name, item.name, counts)
                component_owned = self._crafted_component_count(item.unique_name, counts)
                pending_owned = self._pending_build_count(item, pending_recipes, blueprint_by_parent)
                owned = max(direct_owned, component_owned, pending_owned)
                self.inventory.upsert(
                    item_id=item.id,
                    owned_count=owned,
                    tradable_count=direct_owned if item.tradable else 0,
                    mastered=item.unique_name in mastered or item.name in mastered,
                    raw=json.dumps(
                        {
                            "direct_owned": direct_owned,
                            "component_owned": component_owned,
                            "pending_owned": pending_owned,
                        }
                    ),
                )

            submitted_trades = self.adapter.read_trades()
            submitted_trade_keys = {(trade_data["source"], trade_data["source_line"]) for trade_data in submitted_trades}
            submitted_trade_sources = {trade_data["source"] for trade_data in submitted_trades}
            for trade_data in submitted_trades:
                self.trades.upsert(
                    Trade(
                        source=trade_data["source"],
                        source_line=trade_data["source_line"],
                        traded_at=trade_data.get("traded_at"),
                        partner=trade_data.get("partner"),
                        classification=trade_data.get("classification"),
                        given_text=trade_data.get("given_text"),
                        received_text=trade_data.get("received_text"),
                    )
                )
            if submitted_trade_sources:
                stale_trades = self.db.scalars(select(Trade).where(Trade.source.in_(submitted_trade_sources))).all()
                for trade in stale_trades:
                    if (trade.source, trade.source_line) not in submitted_trade_keys:
                        trade.duplicate_decision = "deleted"

            run.status = "success"
            run.completed_at = datetime.utcnow()
            run.message = "Sync completed."
            self.db.commit()
            return SyncResult(
                status="success",
                message="AlecaFrame data synced into MySQL.",
                inventory_rows=self.db.scalar(select(func.count()).select_from(Item)) or 0,
                items=len(reference_items),
                trades=self.db.scalar(select(func.count()).select_from(Trade)) or 0,
            )
        except Exception as exc:
            self.db.rollback()
            run.status = "error"
            run.completed_at = datetime.utcnow()
            run.message = str(exc)
            self.db.add(run)
            self.db.commit()
            raise

    def _extract_inventory_facts(self, payload: Any) -> tuple[dict[str, int], set[str]]:
        counts: dict[str, int] = {}
        mastered: set[str] = set()
        equipment_buckets = (
            "Suits",
            "LongGuns",
            "Pistols",
            "Melee",
            "Sentinels",
            "SentinelWeapons",
            "SpaceSuits",
            "SpaceGuns",
            "SpaceMelee",
            "Mechs",
            "OperatorAmps",
        )
        stackable_inventory_buckets = (
            "MiscItems",
            "Recipes",
        )

        if isinstance(payload, dict):
            for bucket in equipment_buckets:
                for entry in payload.get(bucket, []) or []:
                    if not isinstance(entry, dict):
                        continue
                    name = self._first_string(entry, ("ItemType", "itemType", "uniqueName", "name", "Type"))
                    if not name:
                        continue
                    counts[name] = max(counts.get(name, 0), 1)
                    xp = self._first_int(entry, ("XP", "xp")) or 0
                    if xp >= self._mastery_xp_threshold(name):
                        mastered.add(name)

            for entry in payload.get("XPInfo", []) or []:
                if not isinstance(entry, dict):
                    continue
                name = self._first_string(entry, ("ItemType", "itemType", "uniqueName", "name", "Type"))
                xp = self._first_int(entry, ("XP", "xp")) or 0
                if name and xp >= self._mastery_xp_threshold(name):
                    mastered.add(name)

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                name = self._first_string(value, ("ItemType", "ItemId", "itemType", "itemId", "uniqueName", "name", "Type"))
                count = self._first_int(value, ("ItemCount", "Count", "count", "amount", "Amount", "quantity"))
                if name and count is not None:
                    counts[name] = max(counts.get(name, 0), count)
                if name and any(bool(value.get(key)) for key in ("Mastered", "mastered", "IsMastered", "completed")):
                    mastered.add(name)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        if isinstance(payload, dict):
            for bucket in stackable_inventory_buckets:
                visit(payload.get(bucket, []))
        return counts, mastered

    @staticmethod
    def _extract_pending_recipe_types(payload: Any) -> set[str]:
        if not isinstance(payload, dict):
            return set()
        pending: set[str] = set()
        for entry in payload.get("PendingRecipes", []) or []:
            if not isinstance(entry, dict):
                continue
            name = SyncService._first_string(entry, ("ItemType", "ItemId", "itemType", "itemId", "uniqueName", "name", "Type"))
            if name:
                pending.add(name)
        return pending

    @staticmethod
    def _pending_build_count(item: Item, pending_recipes: set[str], blueprint_by_parent: dict[str, str]) -> int:
        unique_name = item.unique_name.split("#requires#", 1)[1] if "#requires#" in item.unique_name else item.unique_name
        parent = SyncService._parent_name_from_item_name(item.name)
        parent_blueprint = blueprint_by_parent.get(parent)
        if parent_blueprint and parent_blueprint in pending_recipes:
            return max(1, item.required_count)
        if item.name.endswith(" Blueprint"):
            return 1 if unique_name in pending_recipes else 0
        blueprint_unique = blueprint_by_parent.get(item.name)
        return 1 if blueprint_unique and blueprint_unique in pending_recipes else 0

    @staticmethod
    def _parent_name_from_item_name(name: str) -> str:
        import re

        match = re.match(r"^(.*? Prime)(?:\s|$)", name)
        return match.group(1) if match else name

    @staticmethod
    def _inventory_count_for_item(unique_name: str, name: str, counts: dict[str, int]) -> int:
        if "#requires#" in unique_name:
            unique_name = unique_name.split("#requires#", 1)[1]
        direct = counts.get(unique_name, counts.get(name, 0))
        if direct:
            return direct
        return 0

    @staticmethod
    def _inventory_aliases(unique_name: str) -> list[str]:
        aliases: list[str] = []
        if "/WarframeRecipes/" in unique_name and "Prime" in unique_name:
            aliases.append(unique_name.replace("PrimeChassisBlueprint", "ChassisBlueprint"))
            aliases.append(unique_name.replace("PrimeHelmetBlueprint", "HelmetBlueprint"))
            aliases.append(unique_name.replace("PrimeSystemsBlueprint", "SystemsBlueprint"))
        return [alias for alias in aliases if alias != unique_name]

    @staticmethod
    def _crafted_component_count(unique_name: str, counts: dict[str, int]) -> int:
        if "/WarframeRecipes/" not in unique_name or not unique_name.endswith("Blueprint"):
            return 0
        if not unique_name.endswith(("ChassisBlueprint", "HelmetBlueprint", "SystemsBlueprint")):
            return 0
        component_name = f"{unique_name[:-9]}Component"
        return counts.get(component_name, 0)

    @staticmethod
    def _mastery_xp_threshold(item_type: str) -> int:
        if "/Powersuits/" in item_type or "SentinelPowersuits" in item_type:
            return 900000
        return 450000

    @staticmethod
    def _first_string(value: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    @staticmethod
    def _first_int(value: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        return None
