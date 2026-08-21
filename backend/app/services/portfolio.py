from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.aleca import AlecaAdapter, AlecaAdapterError
from app.models.entities import Item, PortfolioBuildState, PortfolioPartLock, PortfolioSnapshot
from app.schemas.dto import PortfolioHistory, PortfolioSnapshotRow
from app.services.collection import CollectionService


class PortfolioService:
    def __init__(self, db: Session):
        self.db = db
        self.collection = CollectionService(db)

    def snapshot_today(self) -> PortfolioSnapshot:
        today = date.today()
        self._lock_new_consumed_parts(today)
        values = self._current_values()
        existing = self._latest_snapshot()
        if (
            existing is not None
            and values["created_prime_items"] == 0
            and values["unused_prime_parts"] < max(20, existing.unused_prime_parts // 10)
        ):
            return existing
        snapshot = self.db.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.snapshot_date == today))
        if snapshot is None:
            snapshot = PortfolioSnapshot(snapshot_date=today)
            self.db.add(snapshot)
        snapshot.created_prime_items = values["created_prime_items"]
        snapshot.created_prime_parts = values["created_prime_parts"]
        snapshot.unused_prime_parts = values["unused_prime_parts"]
        snapshot.unused_vaulted_parts = values["unused_vaulted_parts"]
        snapshot.vaulted_parts = values["vaulted_parts"]
        snapshot.platinum_balance = values["platinum_balance"]
        snapshot.plat_value = values["plat_value"]
        snapshot.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def _latest_snapshot(self) -> PortfolioSnapshot | None:
        return self.db.scalar(select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_date.desc()))

    def history(self, days: int = 90) -> PortfolioHistory:
        self.snapshot_today()
        limit = max(1, min(days, 3650))
        rows = list(
            self.db.scalars(
                select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_date.desc()).limit(limit)
            )
        )
        history_rows = [self._row(snapshot) for snapshot in reversed(rows)]
        return PortfolioHistory(current=history_rows[-1] if history_rows else None, history=history_rows)

    def _current_values(self) -> dict[str, int | float]:
        rows = self.collection.inventory_rows()
        locks = list(self.db.scalars(select(PortfolioPartLock)))
        states = list(self.db.scalars(select(PortfolioBuildState)))
        groups = self.collection._prime_item_groups(rows)
        created_prime_items = sum(1 for group in groups.values() if group["built"] or group["mastered"])
        created_prime_parts = sum(lock.quantity for lock in locks)
        unused_prime_parts = 0
        unused_vaulted_parts = 0
        locked_vaulted_parts = sum(lock.quantity for lock in locks if lock.vaulted)
        locked_plat_value = sum(lock.quantity * lock.unit_price for lock in locks)
        unused_plat_value = 0.0
        platinum_balance = self._platinum_balance()

        for group in groups.values():
            parts = list(group["parts"])
            for part in parts:
                if self.collection._is_nested_prime_requirement(part):
                    continue
                unused_count = max(0, part.tradable_count - part.pending_count)
                if unused_count <= 0:
                    continue
                unused_prime_parts += unused_count
                if part.vaulted:
                    unused_vaulted_parts += unused_count
                unused_plat_value += unused_count * part.market_value

        return {
            "created_prime_items": created_prime_items,
            "created_prime_parts": created_prime_parts,
            "unused_prime_parts": unused_prime_parts,
            "unused_vaulted_parts": unused_vaulted_parts,
            "vaulted_parts": locked_vaulted_parts + unused_vaulted_parts,
            "platinum_balance": platinum_balance,
            "plat_value": round(locked_plat_value + unused_plat_value + platinum_balance, 2),
        }

    @staticmethod
    def _platinum_balance() -> int:
        try:
            return AlecaAdapter().read_platinum_balance()
        except AlecaAdapterError:
            return 0

    def _lock_new_consumed_parts(self, lock_date: date) -> None:
        rows = self.collection.inventory_rows()
        groups = self.collection._prime_item_groups(rows)
        for group in groups.values():
            parent_name = str(group["parent_name"])
            base = group.get("base")
            parts = [part for part in list(group["parts"]) if not self.collection._is_nested_prime_requirement(part)]
            direct_count = max(0, int(getattr(base, "direct_count", 0) or 0))
            pending_count = max(0, int(getattr(base, "pending_count", 0) or 0))
            built_count = max(direct_count, pending_count)
            if built_count <= 0 and bool(group["mastered"]):
                built_count = 1
            state = self.db.scalar(select(PortfolioBuildState).where(PortfolioBuildState.parent_name == parent_name))
            if state is None:
                state = PortfolioBuildState(parent_name=parent_name, locked_build_count=0)
                self.db.add(state)
                self.db.flush()
            locked_from_rows = self._locked_build_count(parent_name, parts)
            target_locked_count = max(state.locked_build_count, built_count)
            if locked_from_rows > target_locked_count and target_locked_count > 0:
                self._trim_duplicate_locks(parent_name, parts, target_locked_count)
                locked_from_rows = target_locked_count
            current_locked_count = max(state.locked_build_count, locked_from_rows)
            delta = built_count - current_locked_count
            if delta <= 0:
                if state.locked_build_count < current_locked_count:
                    state.locked_build_count = current_locked_count
                    state.updated_at = datetime.utcnow()
                continue
            source = "starting" if current_locked_count == 0 else "build"
            for part in parts:
                quantity = delta * part.required_count
                if quantity <= 0:
                    continue
                self.db.add(
                    PortfolioPartLock(
                        lock_date=lock_date,
                        parent_name=parent_name,
                        part_name=part.name,
                        item_id=self._item_id_for_unique_name(part.unique_name),
                        quantity=quantity,
                        unit_price=part.market_value,
                        vaulted=part.vaulted,
                        source=source,
                    )
                )
            state.locked_build_count = built_count
            state.updated_at = datetime.utcnow()
        self.db.flush()

    def _item_id_for_unique_name(self, unique_name: str) -> int | None:
        return self.db.scalar(select(Item.id).where(Item.unique_name == unique_name))

    def _locked_build_count(self, parent_name: str, parts: list) -> int:
        if not parts:
            return 0
        locks = list(
            self.db.scalars(select(PortfolioPartLock).where(PortfolioPartLock.parent_name == parent_name))
        )
        if not locks:
            return 0
        totals: dict[str, int] = {}
        for lock in locks:
            totals[lock.part_name] = totals.get(lock.part_name, 0) + lock.quantity
        counts = []
        for part in parts:
            required = max(1, int(part.required_count))
            counts.append(totals.get(part.name, 0) // required)
        return min(counts) if counts else 0

    def _trim_duplicate_locks(self, parent_name: str, parts: list, target_build_count: int) -> None:
        for part in parts:
            desired_quantity = target_build_count * max(1, int(part.required_count))
            locks = list(
                self.db.scalars(
                    select(PortfolioPartLock)
                    .where(
                        PortfolioPartLock.parent_name == parent_name,
                        PortfolioPartLock.part_name == part.name,
                    )
                    .order_by(PortfolioPartLock.lock_date.desc(), PortfolioPartLock.id.desc())
                )
            )
            total_quantity = sum(lock.quantity for lock in locks)
            excess = total_quantity - desired_quantity
            if excess <= 0:
                continue
            for lock in locks:
                if excess <= 0:
                    break
                if lock.quantity <= excess:
                    excess -= lock.quantity
                    self.db.delete(lock)
                else:
                    lock.quantity -= excess
                    excess = 0

    @staticmethod
    def _row(snapshot: PortfolioSnapshot) -> PortfolioSnapshotRow:
        return PortfolioSnapshotRow(
            snapshot_date=snapshot.snapshot_date.isoformat(),
            created_prime_items=snapshot.created_prime_items,
            created_prime_parts=snapshot.created_prime_parts,
            unused_prime_parts=snapshot.unused_prime_parts,
            unused_vaulted_parts=snapshot.unused_vaulted_parts,
            vaulted_parts=snapshot.vaulted_parts,
            platinum_balance=snapshot.platinum_balance,
            plat_value=round(snapshot.plat_value, 2),
        )
