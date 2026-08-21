import { useEffect, useMemo, useState } from "react";

import { TradeAnalysisItem, TradeAnalysisResponse, api } from "../api";

function formatPlat(value: number) {
  return `${value.toFixed(0)}p`;
}

function signedPlat(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatPlat(value)}`;
}

function signedNumber(value: number) {
  return `${value > 0 ? "+" : ""}${value}`;
}

function valueClass(value: number) {
  if (value > 0) return "text-emerald-300";
  if (value < 0) return "text-rose-300";
  return "text-slate-300";
}

function formatDate(value: string | null) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatGap(seconds: number | null) {
  if (seconds === null) return "unknown gap";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes <= 0) return `${remainder}s apart`;
  return `${minutes}m ${remainder}s apart`;
}

function itemList(items: TradeAnalysisItem[]) {
  if (items.length === 0) return <span className="text-slate-500">None detected</span>;
  return (
    <div className="space-y-1">
      {items.map((item, index) => (
        <div key={`${item.name}-${index}`} className="flex flex-wrap items-center justify-between gap-2 border border-slate-800 bg-slate-950 px-2 py-1 text-xs">
          <span className={item.matched ? "text-slate-100" : "text-amber-300"}>
            {item.name}{item.quantity > 1 ? ` x${item.quantity}` : ""}{item.vaulted ? " · Vaulted" : ""}{!item.matched ? " · Unmatched" : ""}
          </span>
          <span className="text-slate-300">{formatPlat(item.unit_price)} ea / {formatPlat(item.total_value)}</span>
        </div>
      ))}
    </div>
  );
}

export function TradesPage() {
  const [data, setData] = useState<TradeAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [historicalLoading, setHistoricalLoading] = useState(false);
  const [priceMode, setPriceMode] = useState<"snapshot" | "historical">("snapshot");
  const [search, setSearch] = useState("");
  const [actionTradeId, setActionTradeId] = useState<number | null>(null);

  async function loadAnalysis() {
    setLoading(true);
    setError(null);
    const snapshot = await api.tradeAnalysis(false);
    setData(snapshot);
    setPriceMode("snapshot");
    setLoading(false);
    setHistoricalLoading(true);
    try {
      const historical = await api.tradeAnalysis(true);
      setData(historical);
      setPriceMode("historical");
    } finally {
      setHistoricalLoading(false);
    }
  }

  async function updateDuplicateDecision(tradeId: number, action: "confirm" | "delete") {
    setActionTradeId(tradeId);
    setError(null);
    try {
      if (action === "confirm") await api.confirmTradeDuplicate(tradeId);
      else await api.deleteTradeDuplicate(tradeId);
      setData(await api.tradeAnalysis(priceMode === "historical"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionTradeId(null);
    }
  }

  useEffect(() => {
    let alive = true;
    loadAnalysis().catch((err: unknown) => {
      if (!alive) return;
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
      setHistoricalLoading(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (data?.trades ?? []).filter((trade) => {
      if (!needle) return true;
      return [trade.partner, trade.classification, ...trade.given_items.map((item) => item.name), ...trade.received_items.map((item) => item.name)]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [data, search]);

  if (loading) return <div>Loading trade analysis</div>;
  if (error) return <div className="text-red-300">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-5">
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Trades</div>
          <div className="text-2xl font-semibold">{data.summary.trades}</div>
        </div>
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Plat Balance</div>
          <div className={`text-2xl font-semibold ${valueClass(data.summary.total_balance)}`}>{signedPlat(data.summary.total_balance)}</div>
        </div>
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Vaulted Balance</div>
          <div className={`text-2xl font-semibold ${valueClass(data.summary.vaulted_balance)}`}>{signedNumber(data.summary.vaulted_balance)}</div>
        </div>
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Win / Loss / Mixed / Even</div>
          <div className="text-lg font-semibold text-slate-100">{data.summary.positive_trades} / {data.summary.negative_trades} / {data.summary.mixed_trades} / {data.summary.neutral_trades}</div>
        </div>
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Unmatched Items</div>
          <div className={data.summary.unmatched_items > 0 ? "text-2xl font-semibold text-amber-300" : "text-2xl font-semibold text-slate-100"}>{data.summary.unmatched_items}</div>
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Trades</h1>
          <div className="text-sm text-slate-400">
            {priceMode === "historical" ? "Using historical lowest prices near each trade date." : "Using stored/current lowest prices while historical values update."}
          </div>
        </div>
        <div className="text-sm text-slate-300">{historicalLoading ? "Updating historical prices..." : `${rows.length} shown`}</div>
      </div>

      <input
        className="w-full border border-slate-700 bg-slate-950 px-3 py-2"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search partner or item"
      />

      <div className="space-y-2">
        {rows.map((trade, index) => (
          <article key={`${trade.trade_id}-${trade.traded_at}-${trade.partner}-${index}`} className={`border bg-slate-950 p-3 ${trade.duplicate_review ? "border-amber-500" : "border-slate-800"}`}>
            {trade.duplicate_review && (
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border border-amber-700 bg-amber-950/30 p-3 text-sm">
                <div>
                  <div className="font-semibold text-amber-200">Possible duplicate trade</div>
                  <div className="text-amber-100/80">Same partner and exact same parts as a later consecutive trade, {formatGap(trade.duplicate_gap_seconds)}.</div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void updateDuplicateDecision(trade.trade_id, "confirm")}
                    disabled={actionTradeId === trade.trade_id}
                    className="border border-emerald-500 px-3 py-2 font-semibold text-emerald-100 disabled:border-slate-700 disabled:text-slate-500"
                  >
                    Confirm
                  </button>
                  <button
                    type="button"
                    onClick={() => void updateDuplicateDecision(trade.trade_id, "delete")}
                    disabled={actionTradeId === trade.trade_id}
                    className="border border-rose-500 px-3 py-2 font-semibold text-rose-100 disabled:border-slate-700 disabled:text-slate-500"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}
            <div className="mb-3 grid gap-3 lg:grid-cols-[180px_180px_1fr_120px_120px]">
              <div>
                <div className="text-xs text-slate-500">Date</div>
                <div className="text-sm font-semibold">{formatDate(trade.traded_at)}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Partner</div>
                <div className="text-sm font-semibold">{trade.partner || "Unknown"}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Value</div>
                <div className="text-sm text-slate-200">Gave {formatPlat(trade.given_value)} / Received {formatPlat(trade.received_value)}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Plat Balance</div>
                <div className={`text-lg font-semibold ${valueClass(trade.balance)}`}>{signedPlat(trade.balance)}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Vaulted</div>
                <div className={`text-lg font-semibold ${valueClass(trade.vaulted_balance)}`}>{signedNumber(trade.vaulted_balance)}</div>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-slate-500">You Gave</div>
                {itemList(trade.given_items)}
              </div>
              <div>
                <div className="mb-1 text-xs text-slate-500">You Received</div>
                {itemList(trade.received_items)}
              </div>
            </div>
          </article>
        ))}
        {rows.length === 0 && <div className="border border-slate-800 bg-slate-950 p-4 text-center text-slate-400">No trades found</div>}
      </div>
    </div>
  );
}

