from datetime import datetime

from pydantic import BaseModel


class InventoryRow(BaseModel):
    unique_name: str
    name: str
    category: str
    parent_name: str | None = None
    component_type: str | None = None
    item_type: str
    vaulted: bool
    mastered: bool
    owned_count: int
    required_count: int
    tradable_count: int
    direct_count: int = 0
    pending_count: int = 0
    component_count: int = 0
    safe_to_trade: int
    market_value: float
    collection_value: int


class PrimeItemCountRow(BaseModel):
    label: str
    built: int
    complete_set: int


class CollectionStatusRow(BaseModel):
    label: str
    built: int
    complete_sets: int
    missing_one_part: int
    missing_two_parts: int
    missing_three_parts: int
    missing_four_plus_parts: int


class CollectionStatusMissingPart(BaseModel):
    name: str
    quantity: int
    chat_text: str
    market_value: float = 0


class CollectionStatusDetailItem(BaseModel):
    item_name: str
    vaulted: bool = False
    set_count: int
    missing_parts: list[CollectionStatusMissingPart]
    tradable_parts: list[CollectionStatusMissingPart] = []
    copy_parts: list[CollectionStatusMissingPart] = []
    copy_priority: bool = True
    zero_owned_priority: bool = False
    part_value_each: float = 0
    set_market_value_each: float = 0
    part_value_total: float = 0
    set_market_value_total: float = 0
    non_complete_missing_one_part: int = 0
    non_complete_missing_two_parts: int = 0
    non_complete_missing_three_parts: int = 0
    non_complete_missing_four_plus_parts: int = 0
    missing_one_part_copy_text: str = ""
    missing_two_parts_copy_text: str = ""
    missing_three_parts_copy_text: str = ""
    missing_four_plus_parts_copy_text: str = ""


class CollectionStatusDetail(BaseModel):
    row: str
    column: str
    label: str
    copy_text: str
    items: list[CollectionStatusDetailItem]
    complete_part_value_total: float = 0
    complete_set_market_value_total: float = 0
    non_complete_missing_one_part: int = 0
    non_complete_missing_two_parts: int = 0
    non_complete_missing_three_parts: int = 0
    non_complete_missing_four_plus_parts: int = 0


class TradingPositionBucket(BaseModel):
    parts: float
    plat: float


class TradingPositionRow(BaseModel):
    label: str
    vaulted: TradingPositionBucket
    not_vaulted: TradingPositionBucket
    total: TradingPositionBucket


class Dashboard(BaseModel):
    prime_completion_percent: float
    trading_capital: float
    vaulted_value: float
    unvaulted_value: float
    duplicate_parts: int
    missing_prime_items: int
    missing_prime_parts: int
    total_prime_parts: int
    tradable_prime_parts: int
    missing_one_part: int
    missing_two_parts: int
    missing_three_parts: int
    missing_four_parts: int
    completion_by_category: dict[str, float]
    prime_item_counts: list[PrimeItemCountRow]
    collection_status: list[CollectionStatusRow]
    trading_position: list[TradingPositionRow]


class MissingItem(BaseModel):
    name: str
    category: str
    item_type: str
    missing_parts: list[str]
    collection_percent: float
    collection_gain_score: int
    image: str | None = None


class TradablePartRow(BaseModel):
    unique_name: str
    name: str
    item_name: str
    item_type: str
    category: str
    vaulted: bool
    status: str
    quantity: int
    owned_count: int
    required_count: int
    market_value: float
    total_value: float
    reason: str
    chat_text: str


class StrategicAssetRow(BaseModel):
    side: str
    tier: str
    name: str
    item_name: str
    vaulted: bool
    quantity: int
    market_value: float
    total_value: float
    chat_text: str


class StrategicAssets(BaseModel):
    max_part_value: float
    crown_min_value: float
    strategic_min_value: float
    owned: list[StrategicAssetRow]
    missing: list[StrategicAssetRow]
    junk: list[StrategicAssetRow]


class PricingProfile(BaseModel):
    price_source: str
    calculation_method: str
    margin: str
    rounding: str


class TradeFrameSettings(BaseModel):
    sell: PricingProfile
    buy: PricingProfile
    tf_calculations: PricingProfile
    warframe_chat_max_length: int
    warframe_chat_margin: int
    aleca_data_dir: str
    aleca_data_dir_valid: bool = False
    aleca_data_dir_status: str = ""


class TradeFrameSettingsUpdate(BaseModel):
    sell: PricingProfile | None = None
    buy: PricingProfile | None = None
    tf_calculations: PricingProfile | None = None
    warframe_chat_max_length: int | None = None
    warframe_chat_margin: int | None = None
    aleca_data_dir: str | None = None


class DuplicateItem(BaseModel):
    name: str
    category: str
    vaulted: bool
    count: int
    safe_trade_count: int
    keep_count: int
    market_value: float
    collection_value: int


class TradeRecommendation(BaseModel):
    give: str
    receive: str
    collection_gain_score: int
    market_delta: float
    reason: str


class TradeAnalysisItem(BaseModel):
    name: str
    quantity: int
    unit_price: float
    total_value: float
    vaulted: bool
    matched: bool


class TradeAnalysisRow(BaseModel):
    trade_id: int
    traded_at: datetime | None
    partner: str | None
    classification: str | None
    given_items: list[TradeAnalysisItem]
    received_items: list[TradeAnalysisItem]
    given_value: float
    received_value: float
    balance: float
    vaulted_balance: int
    duplicate_review: bool = False
    duplicate_gap_seconds: int | None = None
    duplicate_decision: str | None = None


class TradeAnalysisSummary(BaseModel):
    trades: int
    total_balance: float
    positive_trades: int
    negative_trades: int
    neutral_trades: int
    mixed_trades: int = 0
    vaulted_balance: int
    unmatched_items: int


class TradeAnalysisResponse(BaseModel):
    summary: TradeAnalysisSummary
    trades: list[TradeAnalysisRow]


class TradeRow(BaseModel):
    id: int
    traded_at: datetime | None
    partner: str | None
    classification: str | None
    given_text: str | None
    received_text: str | None
    market_delta: float
    collection_gain: int
    duplicate_decision: str | None = None




class PortfolioSnapshotRow(BaseModel):
    snapshot_date: str
    created_prime_items: int
    created_prime_parts: int
    unused_prime_parts: int
    unused_vaulted_parts: int
    vaulted_parts: int
    platinum_balance: int = 0
    plat_value: float


class PortfolioHistory(BaseModel):
    current: PortfolioSnapshotRow | None
    history: list[PortfolioSnapshotRow]


class SyncResult(BaseModel):
    status: str
    message: str
    inventory_rows: int
    items: int
    trades: int


class MarketImportResult(BaseModel):
    status: str
    message: str
    fetched: int
    updated: int
    skipped: int
    failed: int


class MarketMatchItem(BaseModel):
    name: str
    chat_text: str
    quantity: int
    market_value: float
    platinum: float = 0
    lead_tags: list[str] = []


class MarketUserMatch(BaseModel):
    user_name: str
    user_slug: str
    status: str | None = None
    last_seen: str | None = None
    reputation: int | None = None
    trade_fit_score: float = 0
    they_sell: list[MarketMatchItem]
    they_buy: list[MarketMatchItem]
    copy_texts: list[str]


class MarketMatchResponse(BaseModel):
    matches: list[MarketUserMatch]
    scan_owned_missing: list[int] = []
    scan_not_missing: list[int] = []
    missing_items_checked: int
    missing_part_quantity_checked: int = 0
    missing_part_types_total: int = 0
    missing_part_quantity_total: int = 0
    users_checked: int
    errors: list[str] = []
    generated_at: str | None = None
    refreshing: bool = False
