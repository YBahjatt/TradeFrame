from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unique_name: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    parent_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    component_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vaulted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    tradable: Mapped[bool] = mapped_column(Boolean, default=True)
    required_count: Mapped[int] = mapped_column(Integer, default=1)
    image: Mapped[str | None] = mapped_column(String(512), nullable=True)

    inventory: Mapped["Inventory | None"] = relationship(back_populates="item")


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), unique=True, index=True)
    owned_count: Mapped[int] = mapped_column(Integer, default=0)
    tradable_count: Mapped[int] = mapped_column(Integer, default=0)
    mastered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    item: Mapped[Item] = relationship(back_populates="inventory")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("source", "source_line", name="uq_trade_source_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(512), index=True)
    source_line: Mapped[int] = mapped_column(Integer)
    traded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    partner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    given_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_delta: Mapped[float] = mapped_column(Float, default=0)
    collection_gain: Mapped[int] = mapped_column(Integer, default=0)
    analysis_given_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_received_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_given_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_received_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_priced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    analysis_price_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duplicate_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    current_price: Mapped[float] = mapped_column(Float, default=0)
    average_price: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(64), default="warframe.market")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ScoringWeight(Base):
    __tablename__ = "scoring_weights"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    created_prime_items: Mapped[int] = mapped_column(Integer, default=0)
    created_prime_parts: Mapped[int] = mapped_column(Integer, default=0)
    unused_prime_parts: Mapped[int] = mapped_column(Integer, default=0)
    unused_vaulted_parts: Mapped[int] = mapped_column(Integer, default=0)
    vaulted_parts: Mapped[int] = mapped_column(Integer, default=0)
    platinum_balance: Mapped[int] = mapped_column(Integer, default=0)
    plat_value: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PortfolioBuildState(Base):
    __tablename__ = "portfolio_build_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    locked_build_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PortfolioPartLock(Base):
    __tablename__ = "portfolio_part_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lock_date: Mapped[date] = mapped_column(Date, index=True)
    parent_name: Mapped[str] = mapped_column(String(255), index=True)
    part_name: Mapped[str] = mapped_column(String(255), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    vaulted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="build")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
