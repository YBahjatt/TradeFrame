from collections import defaultdict
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Inventory, Item
from app.repositories.base import PriceRepository, WeightRepository
from app.schemas.dto import CollectionStatusDetail, CollectionStatusDetailItem, CollectionStatusMissingPart, CollectionStatusRow, Dashboard, DuplicateItem, InventoryRow, MissingItem, PrimeItemCountRow, StrategicAssetRow, StrategicAssets, TradablePartRow, TradeRecommendation, TradingPositionBucket, TradingPositionRow
from app.services.scoring import ScoringService
from app.services.settings import SettingsService


class CollectionService:
    def __init__(self, db: Session):
        self.db = db
        self.prices = PriceRepository(db)
        self.scoring = ScoringService(WeightRepository(db).as_dict())
        self.settings = SettingsService(db)

    def inventory_rows(self) -> list[InventoryRow]:
        rows = []
        tf_pricing = self.settings.get().tf_calculations
        for item, inventory in self._item_inventory_pairs():
            price = self.prices.price_for_item(item.id)
            current_price = self.settings.apply_pricing(price.current_price if price else 0, tf_pricing)
            tradable_count = inventory.tradable_count if inventory else 0
            raw_counts = self._inventory_raw_counts(inventory.raw if inventory else None)
            direct_count = raw_counts.get("direct_owned", inventory.owned_count if inventory else 0)
            pending_count = raw_counts.get("pending_owned", 0)
            component_count = raw_counts.get("component_owned", 0)
            owned_count = inventory.owned_count if inventory else 0
            if item.component_type == "nested_prime_requirement":
                owned_count = 0
                direct_count = 0
                pending_count = 0
                component_count = 0
                tradable_count = 0
            safe_count = max(0, tradable_count - pending_count)
            rows.append(
                InventoryRow(
                    unique_name=item.unique_name,
                    name=item.name,
                    category=item.category,
                    parent_name=item.parent_name,
                    component_type=item.component_type,
                    item_type=self._item_type_from_unique_name(item.unique_name),
                    vaulted=item.vaulted,
                    mastered=bool(inventory.mastered) if inventory else False,
                    owned_count=owned_count,
                    required_count=item.required_count,
                    tradable_count=tradable_count,
                    direct_count=direct_count,
                    pending_count=pending_count,
                    component_count=component_count,
                    safe_to_trade=safe_count,
                    market_value=current_price,
                    collection_value=self.scoring.score_gain(item, inventory.owned_count if inventory else 0),
                )
            )
        parent_types = {
            row.name: row.item_type
            for row in rows
            if row.parent_name == row.name or row.name == self._parent_key(row)
        }
        return [
            row.model_copy(update={"item_type": parent_types.get(row.parent_name or self._parent_key(row), row.item_type)})
            for row in rows
        ]

    def dashboard(self) -> Dashboard:
        rows = self.inventory_rows()
        prime_groups = self._prime_item_groups(rows)
        prime_part_rows = [part for group in prime_groups.values() for part in group["parts"]]
        tradable_part_rows = self.tradable_parts("tradable", None)
        missing_counts = [sum(1 for part in group["parts"] if part.owned_count <= 0) for group in prime_groups.values()]
        missing_prime_items = sum(1 for group in prime_groups.values() if not group["built"] and not group["mastered"])
        by_category: dict[str, list[InventoryRow]] = defaultdict(list)
        for row in prime_part_rows:
            by_category[row.category].append(row)
        completion_by_category = {
            category: round(100 * sum(1 for row in group if row.owned_count > 0) / len(group), 2)
            for category, group in by_category.items()
            if group
        }
        prime_item_counts = self._prime_item_counts(rows)
        built_total = next((row.built for row in prime_item_counts if row.label == "Total"), 0)
        prime_item_total = len(prime_groups)
        collection_status = self._collection_status(prime_groups)
        trading_position = self._trading_position(prime_groups)
        missing_position_parts = next((row.total.parts for row in trading_position if row.label == "Missing"), 0)
        return Dashboard(
            prime_completion_percent=round(100 * built_total / prime_item_total, 2) if prime_item_total else 0,
            trading_capital=sum(row.total_value for row in tradable_part_rows),
            vaulted_value=sum(row.total_value for row in tradable_part_rows if row.vaulted),
            unvaulted_value=sum(row.total_value for row in tradable_part_rows if not row.vaulted),
            duplicate_parts=sum(row.quantity for row in tradable_part_rows),
            missing_prime_items=missing_prime_items,
            missing_prime_parts=missing_position_parts,
            total_prime_parts=sum(row.owned_count for row in prime_part_rows),
            tradable_prime_parts=self._tradable_prime_parts(prime_groups),
            missing_one_part=sum(1 for count in missing_counts if count == 1),
            missing_two_parts=sum(1 for count in missing_counts if count == 2),
            missing_three_parts=sum(1 for count in missing_counts if count == 3),
            missing_four_parts=sum(1 for count in missing_counts if count >= 4),
            completion_by_category=completion_by_category,
            prime_item_counts=prime_item_counts,
            collection_status=collection_status,
            trading_position=trading_position,
        )


    def collection_status_detail(self, row: str, column: str) -> CollectionStatusDetail:
        rows = self.inventory_rows()
        price_by_part = {item.name: item.market_value for item in rows}
        groups = self._prime_item_groups(rows)
        selected_groups = self._collection_status_groups(groups, row)
        items: list[CollectionStatusDetailItem] = []
        non_complete_buckets = {1: 0, 2: 0, 3: 0, 4: 0}
        selected_bucket = self._missing_column_bucket(column)

        for group in sorted(selected_groups, key=lambda candidate: str(candidate["parent_name"])):
            item_name = str(group["parent_name"])
            parts = self._set_math_parts(group)
            base = group.get("base")
            if row == "not":
                complete_count, actionable_partial_sets = self._first_set_details(parts)
            else:
                complete_count, partial_sets = self._set_multiplicity_details(parts)
                actionable_partial_sets = self._actionable_partial_sets(parts, partial_sets)
            for missing in actionable_partial_sets:
                non_complete_buckets[self._missing_bucket(sum(missing.values()))] += 1

            if column == "built":
                missing = self._first_build_missing_parts(parts)
                items.append(
                    self._collection_detail_item(
                        item_name,
                        1,
                        missing,
                        copy_missing=self._tradable_missing_copy_parts(parts, missing),
                        vaulted=self._group_vaulted(group),
                        price_by_part=price_by_part,
                    )
                )
                continue

            if column == "complete_sets":
                if complete_count > 0:
                    part_value_each = self._complete_set_part_value(parts)
                    set_market_value_each = base.market_value if isinstance(base, InventoryRow) else 0
                    items.append(
                        self._collection_detail_item(
                            item_name,
                            complete_count,
                            {},
                            vaulted=self._group_vaulted(group),
                            part_value_each=part_value_each,
                            set_market_value_each=set_market_value_each,
                            partial_sets=actionable_partial_sets,
                            parts_for_copy=parts,
                            price_by_part=price_by_part,
                        )
                    )
                continue

            if selected_bucket is None:
                continue
            partial_buckets = [self._missing_bucket(sum(missing.values())) for missing in actionable_partial_sets]
            copy_priority = not any(bucket < selected_bucket for bucket in partial_buckets)
            matching_sets = [missing for missing in actionable_partial_sets if self._missing_bucket(sum(missing.values())) == selected_bucket]
            for missing in matching_sets:
                copy_missing = missing if copy_priority else {}
                copy_missing = self._tradable_missing_copy_parts(parts, copy_missing)
                items.append(
                    self._collection_detail_item(
                        item_name,
                        1,
                        missing,
                        copy_missing=copy_missing,
                        copy_priority=copy_priority,
                        zero_owned_priority=row == "not" and self._zero_owned_missing_set(parts, missing),
                        tradable_parts=self._partial_set_owned_parts(parts, missing) if row == "owned_mastered" else None,
                        vaulted=self._group_vaulted(group),
                        price_by_part=price_by_part,
                    )
                )

        if selected_bucket is not None:
            items = self._merge_collection_detail_items(items)
            items.sort(
                key=lambda item: (
                    0 if item.zero_owned_priority else 1,
                    0 if item.copy_priority else 1,
                    -self._missing_parts_value(item, price_by_part),
                    item.item_name,
                )
            )
        elif row == "not":
            items.sort(key=lambda item: (-self._missing_parts_value(item, price_by_part), item.item_name))

        copy_parts: list[str] = []
        for item in items:
            for part in item.copy_parts:
                suffix = f" x{part.quantity}" if part.quantity > 1 else ""
                copy_parts.append(f"{part.chat_text}{suffix}")
        return CollectionStatusDetail(
            row=row,
            column=column,
            label=f"{self._collection_row_label(row)} / {self._collection_column_label(column)}",
            copy_text=self._copy_part_list(copy_parts),
            items=items,
            complete_part_value_total=round(sum(item.part_value_total for item in items), 2),
            complete_set_market_value_total=round(sum(item.set_market_value_total for item in items), 2),
            non_complete_missing_one_part=non_complete_buckets[1],
            non_complete_missing_two_parts=non_complete_buckets[2],
            non_complete_missing_three_parts=non_complete_buckets[3],
            non_complete_missing_four_plus_parts=non_complete_buckets[4],
        )

    @staticmethod
    def _merge_collection_detail_items(items: list[CollectionStatusDetailItem]) -> list[CollectionStatusDetailItem]:
        merged: dict[tuple[str, bool, bool], CollectionStatusDetailItem] = {}
        for item in items:
            key = (item.item_name, item.vaulted, item.copy_priority)
            current = merged.get(key)
            if current is None:
                merged[key] = item
                continue
            current.set_count += item.set_count
            current.zero_owned_priority = current.zero_owned_priority or item.zero_owned_priority
            current.missing_parts = CollectionService._sum_collection_parts(current.missing_parts, item.missing_parts)
            current.tradable_parts = CollectionService._sum_collection_parts(current.tradable_parts, item.tradable_parts)
            current.copy_parts = CollectionService._sum_collection_parts(current.copy_parts, item.copy_parts)
        return list(merged.values())

    @staticmethod
    def _sum_collection_parts(
        left: list[CollectionStatusMissingPart],
        right: list[CollectionStatusMissingPart],
    ) -> list[CollectionStatusMissingPart]:
        totals: dict[str, int] = defaultdict(int)
        prices: dict[str, float] = {}
        for part in [*left, *right]:
            totals[part.name] += part.quantity
            prices[part.name] = max(prices.get(part.name, 0), part.market_value)
        return CollectionService._collection_missing_parts(dict(totals), prices)

    def missing_collection(self) -> list[MissingItem]:
        rows = self.inventory_rows()
        by_parent = self._missing_by_parent(rows)
        all_by_parent: dict[str, list[InventoryRow]] = defaultdict(list)
        for row in rows:
            all_by_parent[self._parent_key(row)].append(row)
        result = []
        for parent, missing in by_parent.items():
            group = all_by_parent[parent]
            total = len(group)
            owned = total - len(missing)
            first = group[0]
            result.append(
                MissingItem(
                    name=parent,
                    category=first.category,
                    item_type=first.item_type,
                    missing_parts=[row.name for row in missing],
                    collection_percent=round(100 * owned / total, 2) if total else 0,
                    collection_gain_score=max(row.collection_value for row in missing),
                )
            )
        return sorted(result, key=lambda row: (-row.collection_gain_score, len(row.missing_parts), row.name))


    def tradable_parts(self, status: str | None = None, vaulted: str | None = None) -> list[TradablePartRow]:
        rows = self.inventory_rows()
        groups = self._prime_item_groups(rows)
        result: list[TradablePartRow] = []
        for group in groups.values():
            item_name = str(group["parent_name"])
            needs_first_build = not bool(group["built"] or group["mastered"])
            active_build = self._active_build_group(group)
            for part in group["parts"]:
                if self._is_nested_prime_requirement(part):
                    continue
                if vaulted == "vaulted" and not part.vaulted:
                    continue
                if vaulted == "not_vaulted" and part.vaulted:
                    continue
                if needs_first_build:
                    tradable_count = self._first_build_tradable_surplus(part)
                    missing_count = max(0, part.required_count - part.owned_count)
                    tradable_reason = "Surplus after keeping first-build requirements"
                    missing_reason = "Needed for first build"
                else:
                    tradable_count = self._built_item_tradable_surplus(part, active_build)
                    missing_count = 0
                    tradable_reason = "Item is built or mastered"
                    missing_reason = ""
                if status in (None, "tradable", "position") and tradable_count > 0:
                    result.append(self._tradable_part_row(part, item_name, "Tradable", tradable_count, tradable_reason))
                if status in (None, "missing", "position") and missing_count > 0:
                    result.append(self._tradable_part_row(part, item_name, "Missing", missing_count, missing_reason))
        return sorted(result, key=lambda row: (row.status != "Tradable", not row.vaulted, row.item_name, row.name))

    def strategic_assets(self) -> StrategicAssets:
        groups = self._prime_item_groups(self.inventory_rows())
        full_set_item_names = {
            str(group["parent_name"])
            for group in groups.values()
            if self._set_multiplicity_details(self._set_math_parts(group))[0] > 0
        }
        priced_tradable = [part for part in self.tradable_parts("tradable", None) if part.market_value > 0]
        tradable = sorted(
            priced_tradable,
            key=lambda part: (-part.market_value, -part.total_value, part.name),
        )[:10]
        missing_parts = sorted(
            (part for part in self.tradable_parts("missing", None) if part.market_value > 0),
            key=lambda part: (-part.market_value, -part.total_value, part.name),
        )[:10]
        junk_parts = sorted(
            (part for part in priced_tradable if part.item_name not in full_set_item_names),
            key=lambda part: (part.market_value, part.total_value, part.name),
        )[:10]
        ranked = sorted(
            [("Owned", part) for part in tradable] + [("Missing", part) for part in missing_parts],
            key=lambda candidate: (-candidate[1].market_value, -candidate[1].total_value, candidate[0], candidate[1].name),
        )
        tiers = {
            self._strategic_asset_key(side, part): ("Crown Jewels" if index < 5 else "Strategic")
            for index, (side, part) in enumerate(ranked)
        }
        max_value = ranked[0][1].market_value if ranked else 0
        crown_min = min((part.market_value for _, part in ranked[:5]), default=0)
        strategic_min = min((part.market_value for _, part in ranked[5:]), default=0)
        owned = [
            self._strategic_asset_row(part, "Owned", tiers[self._strategic_asset_key("Owned", part)])
            for part in tradable
        ]
        missing = [
            self._strategic_asset_row(part, "Missing", tiers[self._strategic_asset_key("Missing", part)])
            for part in missing_parts
        ]
        junk = [
            self._strategic_asset_row(part, "Junk", "Junk")
            for part in junk_parts
        ]
        return StrategicAssets(
            max_part_value=round(max_value, 2),
            crown_min_value=crown_min,
            strategic_min_value=strategic_min,
            owned=owned,
            missing=missing,
            junk=junk,
        )

    @staticmethod
    def _strategic_asset_key(side: str, part: TradablePartRow) -> tuple[str, str, str, str]:
        return (side, part.name, part.item_name, part.status)

    @staticmethod
    def _missing_parts_value(item: CollectionStatusDetailItem, price_by_part: dict[str, float]) -> float:
        return sum(part.quantity * price_by_part.get(part.name, 0) for part in item.missing_parts)

    @staticmethod
    def _strategic_asset_row(part: TradablePartRow, side: str, tier: str | None) -> StrategicAssetRow:
        return StrategicAssetRow(
            side=side,
            tier=tier or "",
            name=part.name,
            item_name=part.item_name,
            vaulted=part.vaulted,
            quantity=part.quantity,
            market_value=part.market_value,
            total_value=part.total_value,
            chat_text=part.chat_text,
        )

    @staticmethod
    def _tradable_part_row(part: InventoryRow, item_name: str, status: str, quantity: int, reason: str) -> TradablePartRow:
        return TradablePartRow(
            unique_name=part.unique_name,
            name=part.name,
            item_name=item_name,
            item_type=part.item_type,
            category=part.category,
            vaulted=part.vaulted,
            status=status,
            quantity=quantity,
            owned_count=part.owned_count,
            required_count=part.required_count,
            market_value=part.market_value,
            total_value=round(quantity * part.market_value, 2),
            reason=reason,
            chat_text=CollectionService._chat_link(part.name),
        )

    def duplicates(self) -> list[DuplicateItem]:
        result = []
        for row in self.tradable_parts("tradable", None):
            result.append(
                DuplicateItem(
                    name=row.name,
                    category=row.category,
                    vaulted=row.vaulted,
                    count=row.owned_count,
                    safe_trade_count=row.quantity,
                    keep_count=max(0, row.owned_count - row.quantity),
                    market_value=row.market_value,
                    collection_value=0,
                )
            )
        return sorted(result, key=lambda row: (not row.vaulted, -row.safe_trade_count, row.name))

    def recommendations(self) -> list[TradeRecommendation]:
        duplicates = self.duplicates()
        missing = [part for card in self.missing_collection() for part in card.missing_parts]
        rows = {row.name: row for row in self.inventory_rows()}
        recs: list[TradeRecommendation] = []
        for duplicate in duplicates[:50]:
            give_row = rows[duplicate.name]
            for receive_name in missing[:50]:
                receive_row = rows[receive_name]
                score = receive_row.collection_value + self.scoring.score_loss(give_row.owned_count, 1)
                if score <= 0:
                    continue
                recs.append(
                    TradeRecommendation(
                        give=duplicate.name,
                        receive=receive_name,
                        collection_gain_score=score,
                        market_delta=receive_row.market_value - give_row.market_value,
                        reason=f"Safe duplicate; receiving {receive_name} improves collection progress.",
                    )
                )
        return sorted(recs, key=lambda row: (-row.collection_gain_score, -row.market_delta))[:100]

    def _item_inventory_pairs(self) -> list[tuple[Item, Inventory | None]]:
        stmt = select(Item, Inventory).outerjoin(Inventory, Inventory.item_id == Item.id).order_by(Item.category, Item.name)
        return list(self.db.execute(stmt).all())


    @staticmethod
    def _collection_status_groups(groups: dict[str, dict[str, object]], row: str) -> list[dict[str, object]]:
        if row == "owned_mastered":
            return [group for group in groups.values() if (group["built"] or group["mastered"]) and CollectionService._has_set_parts(group)]
        if row == "not":
            return [group for group in groups.values() if not group["built"] and not group["mastered"] and CollectionService._has_set_parts(group)]
        return []

    @staticmethod
    def _collection_row_label(row: str) -> str:
        return {"owned_mastered": "Owned/Mastered", "not": "Not"}.get(row, row)

    @staticmethod
    def _collection_column_label(column: str) -> str:
        return {
            "built": "Built",
            "complete_sets": "Complete Sets",
            "missing_one_part": "Missing 1 Part",
            "missing_two_parts": "Missing 2 Parts",
            "missing_three_parts": "Missing 3 Parts",
            "missing_four_plus_parts": "Missing 4+ Parts",
        }.get(column, column)

    @staticmethod
    def _missing_column_bucket(column: str) -> int | None:
        return {
            "missing_one_part": 1,
            "missing_two_parts": 2,
            "missing_three_parts": 3,
            "missing_four_plus_parts": 4,
        }.get(column)

    @staticmethod
    def _missing_bucket(missing_count: int) -> int:
        return min(missing_count, 4)

    @staticmethod
    def _first_build_missing_parts(parts: list[InventoryRow]) -> dict[str, int]:
        return {part.name: max(0, part.required_count - part.owned_count) for part in parts if part.owned_count < part.required_count}

    @staticmethod
    def _zero_owned_missing_set(parts: list[InventoryRow], missing: dict[str, int]) -> bool:
        if not parts or not missing:
            return False
        return all(missing.get(part.name, 0) >= part.required_count for part in parts)

    @staticmethod
    def _partial_set_owned_parts(parts: list[InventoryRow], missing: dict[str, int]) -> dict[str, int]:
        owned: dict[str, int] = {}
        for part in parts:
            if CollectionService._is_nested_prime_requirement(part):
                continue
            quantity = part.required_count - missing.get(part.name, 0)
            if quantity > 0:
                owned[part.name] = quantity
        return owned

    @staticmethod
    def _tradable_missing_copy_parts(parts: list[InventoryRow], missing: dict[str, int]) -> dict[str, int]:
        part_by_name = {part.name: part for part in parts}
        return {
            name: quantity
            for name, quantity in missing.items()
            if not CollectionService._is_nested_prime_requirement(part_by_name.get(name))
        }

    @staticmethod
    def _collection_detail_item(
        item_name: str,
        set_count: int,
        missing: dict[str, int],
        vaulted: bool = False,
        copy_missing: dict[str, int] | None = None,
        copy_priority: bool = True,
        zero_owned_priority: bool = False,
        tradable_parts: dict[str, int] | None = None,
        part_value_each: float = 0,
        set_market_value_each: float = 0,
        partial_sets: list[dict[str, int]] | None = None,
        parts_for_copy: list[InventoryRow] | None = None,
        price_by_part: dict[str, float] | None = None,
    ) -> CollectionStatusDetailItem:
        bucket_counts, bucket_copy = CollectionService._partial_set_bucket_detail(partial_sets or [], parts_for_copy or [])
        display_parts = CollectionService._collection_missing_parts(missing, price_by_part)
        copy_source = missing if copy_missing is None else copy_missing
        return CollectionStatusDetailItem(
            item_name=item_name,
            vaulted=vaulted,
            set_count=set_count,
            missing_parts=display_parts,
            tradable_parts=CollectionService._collection_missing_parts(tradable_parts or {}, price_by_part),
            copy_parts=CollectionService._collection_missing_parts(copy_source, price_by_part),
            copy_priority=copy_priority,
            zero_owned_priority=zero_owned_priority,
            part_value_each=round(part_value_each, 2),
            set_market_value_each=round(set_market_value_each, 2),
            part_value_total=round(part_value_each * set_count, 2),
            set_market_value_total=round(set_market_value_each * set_count, 2),
            non_complete_missing_one_part=bucket_counts[1],
            non_complete_missing_two_parts=bucket_counts[2],
            non_complete_missing_three_parts=bucket_counts[3],
            non_complete_missing_four_plus_parts=bucket_counts[4],
            missing_one_part_copy_text=bucket_copy[1],
            missing_two_parts_copy_text=bucket_copy[2],
            missing_three_parts_copy_text=bucket_copy[3],
            missing_four_plus_parts_copy_text=bucket_copy[4],
        )

    @staticmethod
    def _partial_set_bucket_detail(
        partial_sets: list[dict[str, int]],
        parts_for_copy: list[InventoryRow],
    ) -> tuple[dict[int, int], dict[int, str]]:
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        copy_parts = {1: [], 2: [], 3: [], 4: []}
        for missing in partial_sets:
            bucket = CollectionService._missing_bucket(sum(missing.values()))
            counts[bucket] += 1
            copy_missing = CollectionService._tradable_missing_copy_parts(parts_for_copy, missing) if parts_for_copy else missing
            for name, quantity in sorted(copy_missing.items()):
                suffix = f" x{quantity}" if quantity > 1 else ""
                copy_parts[bucket].append(f"{CollectionService._chat_link(name)}{suffix}")
        return counts, {bucket: CollectionService._copy_part_list(parts) for bucket, parts in copy_parts.items()}

    @staticmethod
    def _copy_part_list(parts: list[str]) -> str:
        return ", ".join(parts)

    @staticmethod
    def _complete_set_part_value(parts: list[InventoryRow]) -> float:
        return sum(part.required_count * part.market_value for part in parts)

    @staticmethod
    def _group_vaulted(group: dict[str, object]) -> bool:
        parts = [part for part in group.get("parts", []) if isinstance(part, InventoryRow)]
        if parts:
            return any(part.vaulted for part in parts)
        base = group.get("base")
        return isinstance(base, InventoryRow) and base.vaulted

    @staticmethod
    def _chat_link(name: str) -> str:
        parent = CollectionService._parent_name_from_part_name(name)
        if name == f"{parent} Blueprint":
            return f"[{parent}] BP"
        if name.endswith(" Blueprint"):
            return f"[{name[:-10]}]"
        return f"[{name}]"

    @staticmethod
    def _parent_name_from_part_name(name: str) -> str:
        match = re.match(r"^(.*? Prime)(?:\s|$)", name)
        if match:
            return match.group(1)
        if name.endswith(" Blueprint"):
            return f"[{name}]"
        return name

    @staticmethod
    def _set_multiplicity_details(parts: list[InventoryRow], include_empty_missing_set: bool = False) -> tuple[int, list[dict[str, int]]]:
        if not parts:
            return 0, []
        complete_count = min(part.owned_count // part.required_count for part in parts)
        remaining = {part.name: part.owned_count - complete_count * part.required_count for part in parts}
        required = {part.name: part.required_count for part in parts}
        partial_sets: list[dict[str, int]] = []
        while any(count > 0 for count in remaining.values()):
            missing = {name: max(0, required[name] - remaining[name]) for name in remaining}
            missing = {name: count for name, count in missing.items() if count > 0}
            if missing:
                partial_sets.append(missing)
            for name in remaining:
                remaining[name] = max(0, remaining[name] - required[name])
        if include_empty_missing_set and complete_count == 0 and not partial_sets and all(count == 0 for count in remaining.values()):
            partial_sets.append(required)
        return complete_count, partial_sets

    @staticmethod
    def _actionable_partial_sets(parts: list[InventoryRow], partial_sets: list[dict[str, int]]) -> list[dict[str, int]]:
        part_by_name = {part.name: part for part in parts}
        actionable = []
        for missing in partial_sets:
            missing_parts = [part_by_name.get(name) for name in missing]
            if missing_parts and all(part is not None and CollectionService._is_nested_prime_requirement(part) for part in missing_parts):
                continue
            actionable.append(missing)
        return actionable

    @staticmethod
    def _first_set_details(parts: list[InventoryRow]) -> tuple[int, list[dict[str, int]]]:
        if not parts:
            return 0, []
        complete_count = min(part.owned_count // part.required_count for part in parts)
        if complete_count > 0:
            return complete_count, []
        missing = {
            part.name: max(0, part.required_count - part.owned_count)
            for part in parts
            if part.owned_count < part.required_count
        }
        return 0, CollectionService._actionable_partial_sets(parts, [missing] if missing else [])

    def _collection_status(self, groups: dict[str, dict[str, object]]) -> list[CollectionStatusRow]:
        owned_or_mastered = [group for group in groups.values() if (group["built"] or group["mastered"]) and self._has_set_parts(group)]
        not_owned_or_mastered = [group for group in groups.values() if not group["built"] and not group["mastered"] and self._has_set_parts(group)]
        return [
            self._collection_status_row("Owned/Mastered", owned_or_mastered),
            self._collection_status_row("Not", not_owned_or_mastered, built_count=len(not_owned_or_mastered)),
        ]

    @staticmethod
    def _has_set_parts(group: dict[str, object]) -> bool:
        return any(isinstance(part, InventoryRow) for part in group.get("parts", []))

    @staticmethod
    def _collection_status_row(label: str, groups: list[dict[str, object]], built_count: int | None = None) -> CollectionStatusRow:
        complete_sets = 0
        missing_buckets = {1: 0, 2: 0, 3: 0, 4: 0}
        for group in groups:
            parts = CollectionService._set_math_parts(group)
            if label == "Not":
                complete_count, partial_sets = CollectionService._first_set_details(parts)
            else:
                complete_count, partial_sets = CollectionService._set_multiplicity_details(parts)
                partial_sets = CollectionService._actionable_partial_sets(parts, partial_sets)
            complete_sets += complete_count
            for missing_count in [sum(missing.values()) for missing in partial_sets]:
                if missing_count <= 0:
                    continue
                missing_buckets[min(missing_count, 4)] += 1
        return CollectionStatusRow(
            label=label,
            built=built_count if built_count is not None else sum(1 for group in groups if group["built"] or group["mastered"]),
            complete_sets=complete_sets,
            missing_one_part=missing_buckets[1],
            missing_two_parts=missing_buckets[2],
            missing_three_parts=missing_buckets[3],
            missing_four_plus_parts=missing_buckets[4],
        )

    @staticmethod
    def _set_multiplicity(parts: list[InventoryRow]) -> tuple[int, list[int]]:
        complete_count, partial_sets = CollectionService._set_multiplicity_details(parts)
        return complete_count, [sum(missing.values()) for missing in partial_sets]

    def _trading_position(self, groups: dict[str, dict[str, object]]) -> list[TradingPositionRow]:
        tradable = self._empty_position_buckets()
        missing = self._empty_position_buckets()
        for group in groups.values():
            needs_first_build = not bool(group["built"] or group["mastered"])
            active_build = self._active_build_group(group)
            for part in group["parts"]:
                if self._is_nested_prime_requirement(part):
                    continue
                key = "vaulted" if part.vaulted else "not_vaulted"
                price = part.market_value
                if needs_first_build:
                    missing_count = max(0, part.required_count - part.owned_count)
                    tradable_count = self._first_build_tradable_surplus(part)
                else:
                    missing_count = 0
                    tradable_count = self._built_item_tradable_surplus(part, active_build)
                self._add_position_bucket(tradable[key], tradable_count, price)
                self._add_position_bucket(missing[key], missing_count, price)

        position = self._empty_position_buckets()
        for key in ("vaulted", "not_vaulted"):
            position[key]["parts"] = tradable[key]["parts"] - missing[key]["parts"]
            position[key]["plat"] = tradable[key]["plat"] - missing[key]["plat"]
        return [
            self._trading_position_row("Tradable", tradable),
            self._trading_position_row("Missing", missing),
            self._trading_position_row("Position", position),
            self._trading_coverage_row(tradable, missing),
        ]

    @staticmethod
    def _empty_position_buckets() -> dict[str, dict[str, float]]:
        return {
            "vaulted": {"parts": 0, "plat": 0.0},
            "not_vaulted": {"parts": 0, "plat": 0.0},
        }

    @staticmethod
    def _add_position_bucket(bucket: dict[str, float], count: int, price: float) -> None:
        bucket["parts"] += count
        bucket["plat"] += count * price

    @staticmethod
    def _trading_position_row(label: str, buckets: dict[str, dict[str, float]]) -> TradingPositionRow:
        vaulted = buckets["vaulted"]
        not_vaulted = buckets["not_vaulted"]
        return TradingPositionRow(
            label=label,
            vaulted=TradingPositionBucket(parts=int(vaulted["parts"]), plat=round(vaulted["plat"], 2)),
            not_vaulted=TradingPositionBucket(parts=int(not_vaulted["parts"]), plat=round(not_vaulted["plat"], 2)),
            total=TradingPositionBucket(
                parts=int(vaulted["parts"] + not_vaulted["parts"]),
                plat=round(vaulted["plat"] + not_vaulted["plat"], 2),
            ),
        )

    @staticmethod
    def _collection_missing_parts(missing: dict[str, int], price_by_part: dict[str, float] | None = None) -> list[CollectionStatusMissingPart]:
        return [
            CollectionStatusMissingPart(
                name=name,
                quantity=quantity,
                chat_text=CollectionService._chat_link(name),
                market_value=round((price_by_part or {}).get(name, 0), 2),
            )
            for name, quantity in sorted(missing.items())
            if quantity > 0
        ]

    @staticmethod
    def _coverage_value(tradable: float, missing: float) -> float:
        if missing <= 0:
            return 100.0 if tradable > 0 else 0.0
        return round((tradable / missing) * 100, 2)

    @staticmethod
    def _trading_coverage_row(tradable: dict[str, dict[str, float]], missing: dict[str, dict[str, float]]) -> TradingPositionRow:
        vaulted = {
            "parts": CollectionService._coverage_value(tradable["vaulted"]["parts"], missing["vaulted"]["parts"]),
            "plat": CollectionService._coverage_value(tradable["vaulted"]["plat"], missing["vaulted"]["plat"]),
        }
        not_vaulted = {
            "parts": CollectionService._coverage_value(tradable["not_vaulted"]["parts"], missing["not_vaulted"]["parts"]),
            "plat": CollectionService._coverage_value(tradable["not_vaulted"]["plat"], missing["not_vaulted"]["plat"]),
        }
        total = {
            "parts": CollectionService._coverage_value(
                tradable["vaulted"]["parts"] + tradable["not_vaulted"]["parts"],
                missing["vaulted"]["parts"] + missing["not_vaulted"]["parts"],
            ),
            "plat": CollectionService._coverage_value(
                tradable["vaulted"]["plat"] + tradable["not_vaulted"]["plat"],
                missing["vaulted"]["plat"] + missing["not_vaulted"]["plat"],
            ),
        }
        return TradingPositionRow(
            label="Coverage",
            vaulted=TradingPositionBucket(parts=vaulted["parts"], plat=vaulted["plat"]),
            not_vaulted=TradingPositionBucket(parts=not_vaulted["parts"], plat=not_vaulted["plat"]),
            total=TradingPositionBucket(parts=total["parts"], plat=total["plat"]),
        )

    def _prime_item_counts(self, rows: list[InventoryRow]) -> list[PrimeItemCountRow]:
        groups = self._prime_item_groups(rows)
        not_owned_nor_mastered = [group for group in groups.values() if not group["built"] and not group["mastered"]]
        return [
            PrimeItemCountRow(
                label="Not Owned nor Mastered",
                built=len(not_owned_nor_mastered),
                complete_set=sum(1 for group in not_owned_nor_mastered if group["complete_set"]),
            ),
            PrimeItemCountRow(
                label="Total",
                built=sum(1 for group in groups.values() if group["built"] or group["mastered"]),
                complete_set=sum(1 for group in groups.values() if group["complete_set"]),
            ),
        ]

    def _prime_item_groups(self, rows: list[InventoryRow]) -> dict[str, dict[str, object]]:
        by_parent: dict[str, list[InventoryRow]] = defaultdict(list)
        for row in rows:
            if " Prime" not in row.name:
                continue
            by_parent[row.parent_name or self._parent_key(row)].append(row)

        groups: dict[str, dict[str, object]] = {}
        for parent, group in by_parent.items():
            base = next((row for row in group if row.name == parent), None)
            parts = [row for row in group if row.name != parent]
            if base is None and len(group) == 1:
                base = group[0]
                parts = []
            if base is None:
                continue
            groups[parent] = {
                "parent_name": parent,
                "base": base,
                "built": base.direct_count > 0 or base.pending_count > 0,
                "in_progress": base.pending_count > 0,
                "mastered": base.mastered,
                "complete_set": bool(parts) and all(part.owned_count >= part.required_count for part in self._set_math_parts({"base": base, "parts": parts})),
                "parts": parts,
            }
        return groups

    @staticmethod
    def _set_math_parts(group: dict[str, object]) -> list[InventoryRow]:
        active_build = CollectionService._active_build_group(group)
        result: list[InventoryRow] = []
        for part in list(group.get("parts", [])):
            if not isinstance(part, InventoryRow):
                continue
            if active_build and part.pending_count > 0:
                result.append(part.model_copy(update={"owned_count": max(0, part.owned_count - part.pending_count)}))
            else:
                result.append(part)
        return result

    @staticmethod
    def _tradable_prime_parts(groups: dict[str, dict[str, object]]) -> int:
        tradable = 0
        for group in groups.values():
            can_trade_all_parts = bool(group["built"] or group["mastered"])
            active_build = CollectionService._active_build_group(group)
            for part in group["parts"]:
                if CollectionService._is_nested_prime_requirement(part):
                    continue
                if can_trade_all_parts:
                    tradable += CollectionService._built_item_tradable_surplus(part, active_build)
                else:
                    tradable += CollectionService._first_build_tradable_surplus(part)
        return tradable

    @staticmethod
    def _first_build_tradable_surplus(part: InventoryRow) -> int:
        non_tradable_coverage = max(0, part.owned_count - part.tradable_count)
        tradable_needed_for_build = max(0, part.required_count - non_tradable_coverage)
        return max(0, part.tradable_count - tradable_needed_for_build)

    @staticmethod
    def _built_item_tradable_surplus(part: InventoryRow, active_build: bool) -> int:
        if active_build:
            return max(0, part.tradable_count - part.pending_count)
        return max(0, part.tradable_count)

    @staticmethod
    def _is_nested_prime_requirement(part: InventoryRow | None) -> bool:
        return bool(part and part.component_type == "nested_prime_requirement")

    @staticmethod
    def _active_build_group(group: dict[str, object]) -> bool:
        base = group.get("base")
        return isinstance(base, InventoryRow) and base.pending_count > 0

    @staticmethod
    def _inventory_raw_counts(raw: str | None) -> dict[str, int]:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(value, dict):
            return {}
        result: dict[str, int] = {}
        for key in ("direct_owned", "component_owned", "pending_owned"):
            candidate = value.get(key, 0)
            if isinstance(candidate, int):
                result[key] = candidate
        return result

    @staticmethod
    def _missing_by_parent(rows: list[InventoryRow]) -> dict[str, list[InventoryRow]]:
        result: dict[str, list[InventoryRow]] = defaultdict(list)
        for row in rows:
            if row.owned_count <= 0:
                result[CollectionService._parent_key(row)].append(row)
        return result

    @staticmethod
    def _parent_key(row: InventoryRow) -> str:
        match = re.match(r"^(.*? Prime)(?:\s|$)", row.name)
        if match:
            return match.group(1)
        for suffix in (" Chassis Blueprint", " Neuroptics Blueprint", " Systems Blueprint", " Helmet Blueprint", " Blueprint", " Chassis", " Neuroptics", " Systems", " Helmet", " Barrel", " Receiver", " Stock", " Blade", " Handle", " Link", " String", " Grip", " Disc", " Ornament", " Cerebrum", " Carapace", " Gauntlet", " Boot", " Pouch", " Stars", " Harness", " Wings"):
            if row.name.endswith(suffix):
                return row.name[: -len(suffix)]
        return row.name

    @staticmethod
    def _item_type_from_unique_name(unique_name: str) -> str:
        path = unique_name.lower()
        if "/sentinels/" in path or "sentinelpowersuits" in path or "kubrows" in path:
            return "Companion"
        if "/archwing/" in path or "/space" in path:
            return "Wing"
        if "/powersuits/" in path:
            return "Warframe"
        if "/melee/" in path:
            return "Melee"
        if any(token in path for token in ("/pistols/", "/pistol/", "/akimbo/", "/throwingweapons/")):
            return "Secondary"
        if any(token in path for token in ("/longguns/", "/rifle/", "/shotgun/", "/bows/", "/sniper/")):
            return "Primary"
        return "Other"
