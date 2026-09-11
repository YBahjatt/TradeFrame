from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.aleca import AlecaAdapter
from app.config import get_settings
from app.database.bootstrap import seed_defaults
from app.database.session import get_db
from app.repositories.base import TradeRepository
from app.schemas.dto import CollectionStatusDetail, Dashboard, DuplicateItem, InventoryRow, MarketImportResult, MarketMatchResponse, MissingItem, PortfolioHistory, StrategicAssets, SyncResult, TradablePartRow, TradeAnalysisResponse, TradeFrameSettings, TradeFrameSettingsUpdate, TradeRecommendation, TradeRow
from app.services.collection import CollectionService
from app.services.market import MarketPriceService
from app.services.market_matches import market_match_cache
from app.services.portfolio import PortfolioService
from app.services.settings import SettingsService
from app.services.sync import SyncService
from app.services.trade_analysis import TradeAnalysisService

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/settings", response_model=TradeFrameSettings)
def settings(db: Session = Depends(get_db)) -> TradeFrameSettings:
    return SettingsService(db).get()


@router.put("/settings", response_model=TradeFrameSettings)
def update_settings(update: TradeFrameSettingsUpdate, db: Session = Depends(get_db)) -> TradeFrameSettings:
    return SettingsService(db).update(update)


@router.post("/sync", response_model=SyncResult)
def sync(db: Session = Depends(get_db)) -> SyncResult:
    seed_defaults(db)
    settings = get_settings()
    adapter = AlecaAdapter(settings.aleca_data_dir)
    result = SyncService(db, adapter).sync()
    PortfolioService(db).snapshot_today()
    return result


@router.post("/market/import", response_model=MarketImportResult)
def import_market_prices(db: Session = Depends(get_db)) -> MarketImportResult:
    settings = get_settings()
    adapter = AlecaAdapter(settings.aleca_data_dir)
    result = MarketPriceService(db, adapter).import_prices()
    PortfolioService(db).snapshot_today()
    return result


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db)) -> Dashboard:
    return CollectionService(db).dashboard()


@router.get("/portfolio/history", response_model=PortfolioHistory)
def portfolio_history(days: int = 90, db: Session = Depends(get_db)) -> PortfolioHistory:
    return PortfolioService(db).history(days)


@router.get("/dashboard/collection-status", response_model=CollectionStatusDetail)
def collection_status_detail(row: str, column: str, db: Session = Depends(get_db)) -> CollectionStatusDetail:
    return CollectionService(db).collection_status_detail(row, column)


@router.get("/inventory", response_model=list[InventoryRow])
def inventory(db: Session = Depends(get_db)) -> list[InventoryRow]:
    return CollectionService(db).inventory_rows()


@router.get("/missing", response_model=list[MissingItem])
def missing(db: Session = Depends(get_db)) -> list[MissingItem]:
    return CollectionService(db).missing_collection()


@router.get("/tradable", response_model=list[TradablePartRow])
def tradable(status: str | None = None, vaulted: str | None = None, db: Session = Depends(get_db)) -> list[TradablePartRow]:
    return CollectionService(db).tradable_parts(status, vaulted)


@router.get("/strategic-assets", response_model=StrategicAssets)
def strategic_assets(db: Session = Depends(get_db)) -> StrategicAssets:
    return CollectionService(db).strategic_assets()


@router.get("/market-matches", response_model=MarketMatchResponse)
def market_matches(
    max_missing_items: int = 0,
    max_users: int = 0,
    scan_owned_missing: str | None = None,
    scan_not_missing: str | None = None,
    apply_scan_scope: bool = False,
    refresh: bool = False,
    status_refresh: bool = False,
) -> MarketMatchResponse:
    scan_filters = None
    if apply_scan_scope:
        scan_filters = _market_lead_filters(scan_owned_missing or "", scan_not_missing or "")
    return market_match_cache.get(max_missing_items=max_missing_items, max_users=max_users, refresh=refresh, scan_filters=scan_filters, status_refresh=status_refresh)


def _market_lead_filters(owned_missing: str, not_missing: str) -> set[tuple[str, int]]:
    filters: set[tuple[str, int]] = set()
    for row_key, text in (("owned_mastered", owned_missing), ("not", not_missing)):
        for raw in text.split(","):
            try:
                bucket = int(raw)
            except ValueError:
                continue
            if bucket in (1, 2, 3, 4):
                filters.add((row_key, bucket))
    return filters


@router.get("/duplicates", response_model=list[DuplicateItem])
def duplicates(db: Session = Depends(get_db)) -> list[DuplicateItem]:
    return CollectionService(db).duplicates()


@router.get("/recommendations", response_model=list[TradeRecommendation])
def recommendations(db: Session = Depends(get_db)) -> list[TradeRecommendation]:
    return CollectionService(db).recommendations()


@router.get("/trades/analysis", response_model=TradeAnalysisResponse)
def trade_analysis(historical: bool = False, db: Session = Depends(get_db)) -> TradeAnalysisResponse:
    settings = get_settings()
    adapter = AlecaAdapter(settings.aleca_data_dir)
    return TradeAnalysisService(db, adapter, use_historical=historical).analyze()


@router.get("/trades", response_model=list[TradeRow])
def trades(db: Session = Depends(get_db)) -> list[TradeRow]:
    return [TradeRow.model_validate(row, from_attributes=True) for row in TradeRepository(db).all()]


@router.post("/trades/{trade_id}/confirm-duplicate")
def confirm_trade_duplicate(trade_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    if not TradeRepository(db).set_duplicate_decision(trade_id, "confirmed"):
        raise HTTPException(status_code=404, detail="Trade not found.")
    return {"status": "ok"}


@router.post("/trades/{trade_id}/delete-duplicate")
def delete_trade_duplicate(trade_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    if not TradeRepository(db).set_duplicate_decision(trade_id, "deleted"):
        raise HTTPException(status_code=404, detail="Trade not found.")
    return {"status": "ok"}
