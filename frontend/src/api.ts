export type Dashboard = {
  prime_completion_percent: number;
  trading_capital: number;
  vaulted_value: number;
  unvaulted_value: number;
  duplicate_parts: number;
  missing_prime_items: number;
  missing_prime_parts: number;
  total_prime_parts: number;
  tradable_prime_parts: number;
  missing_one_part: number;
  missing_two_parts: number;
  missing_three_parts: number;
  missing_four_parts: number;
  completion_by_category: Record<string, number>;
  prime_item_counts: Array<{ label: string; built: number; complete_set: number }>;
  collection_status: Array<{ label: string; built: number; complete_sets: number; missing_one_part: number; missing_two_parts: number; missing_three_parts: number; missing_four_plus_parts: number }>;
  trading_position: Array<{ label: string; vaulted: { parts: number; plat: number }; not_vaulted: { parts: number; plat: number }; total: { parts: number; plat: number } }>;
};

export type CollectionStatusDetail = {
  row: string;
  column: string;
  label: string;
  copy_text: string;
  items: Array<{
    item_name: string;
    vaulted: boolean;
    set_count: number;
    missing_parts: Array<{ name: string; quantity: number; chat_text: string; market_value: number }>;
    tradable_parts: Array<{ name: string; quantity: number; chat_text: string; market_value: number }>;
    copy_parts: Array<{ name: string; quantity: number; chat_text: string; market_value: number }>;
    copy_priority: boolean;
    part_value_each: number;
    set_market_value_each: number;
    part_value_total: number;
    set_market_value_total: number;
    non_complete_missing_one_part: number;
    non_complete_missing_two_parts: number;
    non_complete_missing_three_parts: number;
    non_complete_missing_four_plus_parts: number;
    missing_one_part_copy_text: string;
    missing_two_parts_copy_text: string;
    missing_three_parts_copy_text: string;
    missing_four_plus_parts_copy_text: string;
  }>;
  complete_part_value_total: number;
  complete_set_market_value_total: number;
  non_complete_missing_one_part: number;
  non_complete_missing_two_parts: number;
  non_complete_missing_three_parts: number;
  non_complete_missing_four_plus_parts: number;
};

export type InventoryRow = {
  unique_name: string;
  name: string;
  category: string;
  parent_name: string | null;
  component_type: string | null;
  item_type: string;
  vaulted: boolean;
  mastered: boolean;
  owned_count: number;
  required_count: number;
  tradable_count: number;
  safe_to_trade: number;
  market_value: number;
  collection_value: number;
};

export type MissingItem = {
  name: string;
  category: string;
  item_type: string;
  missing_parts: string[];
  collection_percent: number;
  collection_gain_score: number;
  image: string | null;
};

export type TradablePartRow = {
  unique_name: string;
  name: string;
  item_name: string;
  item_type: string;
  category: string;
  vaulted: boolean;
  status: string;
  quantity: number;
  owned_count: number;
  required_count: number;
  market_value: number;
  total_value: number;
  reason: string;
  chat_text: string;
};

export type DuplicateItem = {
  name: string;
  category: string;
  vaulted: boolean;
  count: number;
  safe_trade_count: number;
  keep_count: number;
  market_value: number;
  collection_value: number;
};

export type Recommendation = {
  give: string;
  receive: string;
  collection_gain_score: number;
  market_delta: number;
  reason: string;
};

export type TradeAnalysisItem = {
  name: string;
  quantity: number;
  unit_price: number;
  total_value: number;
  vaulted: boolean;
  matched: boolean;
};

export type TradeAnalysisRow = {
  trade_id: number;
  traded_at: string | null;
  partner: string | null;
  classification: string | null;
  given_items: TradeAnalysisItem[];
  received_items: TradeAnalysisItem[];
  given_value: number;
  received_value: number;
  balance: number;
  vaulted_balance: number;
  duplicate_review: boolean;
  duplicate_gap_seconds: number | null;
  duplicate_decision: string | null;
};

export type TradeAnalysisResponse = {
  summary: {
    trades: number;
    total_balance: number;
    positive_trades: number;
    negative_trades: number;
    neutral_trades: number;
    mixed_trades: number;
    vaulted_balance: number;
    unmatched_items: number;
  };
  trades: TradeAnalysisRow[];
};

export type PortfolioSnapshotRow = {
  snapshot_date: string;
  created_prime_items: number;
  created_prime_parts: number;
  unused_prime_parts: number;
  unused_vaulted_parts: number;
  vaulted_parts: number;
  platinum_balance: number;
  plat_value: number;
};

export type PortfolioHistory = {
  current: PortfolioSnapshotRow | null;
  history: PortfolioSnapshotRow[];
};

export type StrategicAssetRow = {
  side: string;
  tier: string;
  name: string;
  item_name: string;
  vaulted: boolean;
  quantity: number;
  market_value: number;
  total_value: number;
  chat_text: string;
};

export type StrategicAssets = {
  max_part_value: number;
  crown_min_value: number;
  strategic_min_value: number;
  owned: StrategicAssetRow[];
  missing: StrategicAssetRow[];
  junk: StrategicAssetRow[];
};

export type MarketMatchItem = {
  name: string;
  chat_text: string;
  quantity: number;
  market_value: number;
  platinum: number;
  lead_tags: string[];
};

export type MarketUserMatch = {
  user_name: string;
  user_slug: string;
  status: string | null;
  last_seen: string | null;
  reputation: number | null;
  trade_fit_score: number;
  they_sell: MarketMatchItem[];
  they_buy: MarketMatchItem[];
  copy_texts: string[];
};

export type MarketMatchResponse = {
  matches: MarketUserMatch[];
  scan_owned_missing: number[];
  scan_not_missing: number[];
  missing_items_checked: number;
  missing_part_quantity_checked: number;
  missing_part_types_total: number;
  missing_part_quantity_total: number;
  users_checked: number;
  errors: string[];
  generated_at: string | null;
  refreshing: boolean;
};

export type TradeRow = {
  id: number;
  traded_at: string | null;
  partner: string | null;
  classification: string | null;
  given_text: string | null;
  received_text: string | null;
  market_delta: number;
  collection_gain: number;
  duplicate_decision: string | null;
};

export type PricingProfile = {
  price_source: string;
  calculation_method: string;
  margin: string;
  rounding: string;
};

export type TradeFrameSettings = {
  sell: PricingProfile;
  buy: PricingProfile;
  tf_calculations: PricingProfile;
  warframe_chat_max_length: number;
  warframe_chat_margin: number;
  aleca_data_dir: string;
  aleca_data_dir_valid: boolean;
  aleca_data_dir_status: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export const api = {
  sync: async () => {
    const response = await fetch("/api/sync", { method: "POST" });
    if (!response.ok) throw new Error(await response.text());
    return response.json() as Promise<{ status: string; message: string }>;
  },
  settings: () => getJson<TradeFrameSettings>("/api/settings"),
  saveSettings: (settings: Partial<TradeFrameSettings>) => fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  }).then(async (response) => {
    if (!response.ok) throw new Error(await response.text());
    return response.json() as Promise<TradeFrameSettings>;
  }),
  dashboard: () => getJson<Dashboard>("/api/dashboard"),
  portfolioHistory: (days = 90) => getJson<PortfolioHistory>(`/api/portfolio/history?days=${days}`),
  collectionStatusDetail: (row: string, column: string) => getJson<CollectionStatusDetail>(`/api/dashboard/collection-status?row=${encodeURIComponent(row)}&column=${encodeURIComponent(column)}`),
  inventory: () => getJson<InventoryRow[]>("/api/inventory"),
  missing: () => getJson<MissingItem[]>("/api/missing"),
  tradable: (status?: string, vaulted?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (vaulted) params.set("vaulted", vaulted);
    const query = params.toString();
    return getJson<TradablePartRow[]>(`/api/tradable${query ? `?${query}` : ""}`);
  },
  marketMatches: (refresh = false, scanFilters?: { ownedMissing?: number[]; notMissing?: number[] }, applyScanScope = false, statusRefresh = false) => {
    const params = new URLSearchParams();
    if (refresh) params.set("refresh", "true");
    if (statusRefresh) params.set("status_refresh", "true");
    if (applyScanScope) params.set("apply_scan_scope", "true");
    if (applyScanScope || scanFilters?.ownedMissing?.length) params.set("scan_owned_missing", scanFilters?.ownedMissing?.join(",") ?? "");
    if (applyScanScope || scanFilters?.notMissing?.length) params.set("scan_not_missing", scanFilters?.notMissing?.join(",") ?? "");
    const query = params.toString();
    return getJson<MarketMatchResponse>(`/api/market-matches${query ? `?${query}` : ""}`);
  },
  strategicAssets: () => getJson<StrategicAssets>("/api/strategic-assets"),
  duplicates: () => getJson<DuplicateItem[]>("/api/duplicates"),
  recommendations: () => getJson<Recommendation[]>("/api/recommendations"),
  tradeAnalysis: (historical = false) => getJson<TradeAnalysisResponse>(`/api/trades/analysis${historical ? "?historical=true" : ""}`),
  confirmTradeDuplicate: (tradeId: number) => fetch(`/api/trades/${tradeId}/confirm-duplicate`, { method: "POST" }).then(async (response) => {
    if (!response.ok) throw new Error(await response.text());
    return response.json() as Promise<{ status: string }>;
  }),
  deleteTradeDuplicate: (tradeId: number) => fetch(`/api/trades/${tradeId}/delete-duplicate`, { method: "POST" }).then(async (response) => {
    if (!response.ok) throw new Error(await response.text());
    return response.json() as Promise<{ status: string }>;
  }),
  trades: () => getJson<TradeRow[]>("/api/trades")
};
