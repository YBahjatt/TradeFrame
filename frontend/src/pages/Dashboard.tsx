import { ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "react-plotly.js";

import { api, CollectionStatusDetail, PricingProfile, TradeFrameSettings } from "../api";
import { CopyChunks, CopyOptions, copyText, splitCopyText } from "../components/CopyChunks";
import { useAsync } from "../components/useAsync";

function formatPlat(value: number) {
  return `${value.toFixed(0)}p`;
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

function formatDay(value: string) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
}

function positionClass(value: number) {
  if (value >= 0) return "text-emerald-300";
  return "text-rose-300";
}

function tradingLink(status: string, vaulted: "vaulted" | "not_vaulted" | "total") {
  const params = new URLSearchParams();
  params.set("status", status.toLowerCase());
  if (vaulted !== "total") params.set("vaulted", vaulted);
  return `/tradable?${params.toString()}`;
}

function TradingCell({ to, className, children }: { to?: string; className: string; children: ReactNode }) {
  if (!to) return <td className={className}>{children}</td>;
  return (
    <td className={className}>
      <Link to={to} className="block w-full hover:text-cyan-200">
        {children}
      </Link>
    </td>
  );
}

const collectionColumns = [
  { key: "built", label: "Built" },
  { key: "complete_sets", label: "Complete Sets" },
  { key: "missing_one_part", label: "Missing 1 Part" },
  { key: "missing_two_parts", label: "Missing 2 Parts" },
  { key: "missing_three_parts", label: "Missing 3 Parts" },
  { key: "missing_four_plus_parts", label: "Missing 4+ Parts" }
] as const;

function rowKey(label: string) {
  return label === "Owned/Mastered" ? "owned_mastered" : "not";
}

function applyMargin(value: number, margin: string) {
  const text = margin.trim();
  if (!text) return value;
  const numeric = Number(text.endsWith("%") ? text.slice(0, -1) : text);
  if (!Number.isFinite(numeric)) return value;
  if (text.endsWith("%")) return value * (1 + numeric / 100);
  return value + numeric;
}

function roundPrice(value: number, rounding: string) {
  if (rounding === "up") return Math.ceil(value);
  if (rounding === "down") return Math.floor(value);
  return Math.round(value);
}

function pricedValue(value: number, profile: PricingProfile | undefined) {
  if (!profile || profile.price_source === "no" || value <= 0) return 0;
  return Math.max(0, roundPrice(applyMargin(value, profile.margin), profile.rounding));
}

function sellText(chatText: string, value: number, settings: TradeFrameSettings | null | undefined) {
  const price = pricedValue(value, settings?.sell);
  return price > 0 ? `${chatText} ${price}p` : chatText;
}

function buyText(chatText: string, value: number, settings: TradeFrameSettings | null | undefined) {
  const price = pricedValue(value, settings?.buy);
  return price > 0 ? `${chatText} ${price}p` : chatText;
}

function setListingText(itemName: string, price: number, settings: TradeFrameSettings | null | undefined) {
  return sellText(`[${itemName}]`, price, settings);
}

function copySetListing(itemName: string, price: number, settings: TradeFrameSettings | null | undefined) {
  copyText(`${setListingText(itemName, price, settings)} via TradeFrame`);
}

function selectedSetListingsText(detail: CollectionStatusDetail | null, selectedItems: Set<string>, settings: TradeFrameSettings | null | undefined) {
  if (!detail) return;
  const priced = settings?.sell.price_source !== "no";
  return detail.items
    .filter((item) => selectedItems.has(item.item_name))
    .map((item) => setListingText(item.item_name, item.set_market_value_each, settings))
    .join(priced ? ", " : " ");
}

function formatPartList(parts: Array<{ chat_text: string; market_value?: number }>, settings: TradeFrameSettings | null | undefined, side: "sell" | "buy") {
  const profile = side === "sell" ? settings?.sell : settings?.buy;
  const priced = profile?.price_source !== "no";
  return parts
    .map((part) => (side === "sell" ? sellText(part.chat_text, part.market_value ?? 0, settings) : buyText(part.chat_text, part.market_value ?? 0, settings)))
    .join(priced ? ", " : " ");
}

function uniqueParts(parts: Array<{ name: string; chat_text: string; market_value?: number }>) {
  const unique = new Map<string, { chat_text: string; market_value: number }>();
  for (const part of parts) {
    if (!unique.has(part.name)) unique.set(part.name, { chat_text: part.chat_text, market_value: part.market_value ?? 0 });
  }
  return [...unique.values()];
}

function detailRowKey(itemName: string, index: number) {
  return `${itemName}-${index}`;
}

function selectedTradablePartsText(detail: CollectionStatusDetail | null, selectedRows: Set<string>, settings?: TradeFrameSettings | null) {
  if (!detail) return "";
  const parts = new Map<string, { chat_text: string; market_value: number }>();
  detail.items.forEach((item, index) => {
    if (!selectedRows.has(detailRowKey(item.item_name, index))) return;
    for (const part of item.tradable_parts) {
      if (!parts.has(part.name)) parts.set(part.name, { chat_text: part.chat_text, market_value: part.market_value });
    }
  });
  return formatPartList([...parts.values()], settings, "sell");
}

function detailBuyCopyText(detail: CollectionStatusDetail | null, settings?: TradeFrameSettings | null) {
  if (!detail) return "";
  const parts = uniqueParts(detail.items.flatMap((item) => item.copy_parts));
  if (parts.length > 0) return formatPartList(parts, settings, "buy");
  return detail.copy_text;
}

function CopyBucketCell({ count, text, copyOptions }: { count: number; text: string; copyOptions: CopyOptions }) {
  const chunks = splitCopyText(text, Math.max(20, (copyOptions.maxLength ?? 170) - (copyOptions.margin ?? 0)));
  return (
    <td className="px-2 py-1 text-right">
      {chunks.length <= 1 ? (
        <button
          type="button"
          onClick={() => copyText(chunks[0] ?? "")}
          disabled={chunks.length === 0}
          className="w-full px-2 py-1 text-right font-semibold text-slate-200 hover:bg-slate-800 disabled:text-slate-600 disabled:hover:bg-transparent"
        >
          {count}
        </button>
      ) : (
        <div className="flex flex-col items-end gap-1">
          <div className="font-semibold text-slate-200">{count}</div>
          {chunks.map((chunk, index) => (
            <button
              key={`${index}-${chunk.slice(0, 12)}`}
              type="button"
              onClick={() => copyText(chunk)}
              className="text-xs font-semibold text-cyan-200 hover:text-cyan-100"
            >
              Copy {index + 1}
            </button>
          ))}
        </div>
      )}
    </td>
  );
}

export function DashboardPage() {
  const { data, error, loading } = useAsync(api.dashboard);
  const { data: settings } = useAsync(api.settings);
  const { data: portfolio, error: portfolioError } = useAsync(() => api.portfolioHistory(30));
  const [selectedCell, setSelectedCell] = useState<{ row: string; column: string } | null>(null);
  const [detail, setDetail] = useState<CollectionStatusDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedCompleteItems, setSelectedCompleteItems] = useState<Set<string>>(() => new Set());
  const [selectedTradableRows, setSelectedTradableRows] = useState<Set<string>>(() => new Set());

  async function openCollectionCell(row: string, column: string) {
    if (selectedCell?.row === row && selectedCell?.column === column) {
      setSelectedCell(null);
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      setSelectedCompleteItems(new Set());
      setSelectedTradableRows(new Set());
      return;
    }

    setSelectedCompleteItems(new Set());
    setSelectedTradableRows(new Set());
    setSelectedCell({ row, column });
    setDetailLoading(true);
    setDetailError(null);
    try {
      setDetail(await api.collectionStatusDetail(row, column));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Could not load collection detail.");
    } finally {
      setDetailLoading(false);
    }
  }

  if (loading) return <div>Loading</div>;
  if (error) return <div className="text-red-300">{error}</div>;
  if (!data) return null;

  const selectedCompleteCount = selectedCompleteItems.size;
  const copyOptions: CopyOptions = {
    maxLength: settings?.warframe_chat_max_length,
    margin: settings?.warframe_chat_margin,
  };
  const selectedSetCopyText = selectedSetListingsText(detail, selectedCompleteItems, settings) ?? "";
  const isOwnedMissingDetail = detail?.row === "owned_mastered" && detail.column.startsWith("missing_");
  const selectedTradableCount = selectedTradableRows.size;
  const selectedTradableCopyText = selectedTradablePartsText(detail, selectedTradableRows, settings);
  const detailCopyText = detailBuyCopyText(detail, settings);

  return (
    <div className="space-y-5">
      <section className="grid gap-3 md:grid-cols-4">
        {[
          ["Prime Items Built", `${data.prime_completion_percent}%`],
          ["Missing Prime Items", data.missing_prime_items],
          ["Missing Prime Parts", data.missing_prime_parts],
          ["Tradable Prime Parts", data.tradable_prime_parts]
        ].map(([label, value]) => (
          <div key={label} className="border border-slate-800 bg-slate-950 p-4">
            <div className="text-sm text-slate-400">{label}</div>
            <div className="text-2xl font-semibold">{value}</div>
          </div>
        ))}
      </section>

      <section className="border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-semibold">Portfolio History</div>
            <div className="text-xs text-slate-500">Built item value stays counted after crafting; unused Prime parts are added on top.</div>
          </div>
          {portfolioError && <div className="text-sm text-rose-300">{portfolioError}</div>}
        </div>
        {portfolio?.current ? (
          <div className="space-y-3">
            <div className="grid gap-3 md:grid-cols-7">
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Total Value</div>
                <div className="text-2xl font-semibold">{formatPlat(portfolio.current.plat_value)}</div>
              </div>
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Platinum</div>
                <div className="text-2xl font-semibold">{formatPlat(portfolio.current.platinum_balance)}</div>
              </div>
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Vaulted Parts</div>
                <div className="text-2xl font-semibold">{portfolio.current.vaulted_parts}</div>
              </div>
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Unused Vaulted</div>
                <div className="text-2xl font-semibold">{portfolio.current.unused_vaulted_parts}</div>
              </div>
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Created Items</div>
                <div className="text-2xl font-semibold">{portfolio.current.created_prime_items}</div>
              </div>
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Created Parts</div>
                <div className="text-2xl font-semibold">{portfolio.current.created_prime_parts}</div>
              </div>
              <div className="border border-slate-800 bg-slate-900/60 p-3">
                <div className="text-sm text-slate-400">Unused Parts</div>
                <div className="text-2xl font-semibold">{portfolio.current.unused_prime_parts}</div>
              </div>
            </div>
            <div className="border border-slate-800 bg-slate-900/60 p-3">
              <Plot
                data={[
                  {
                    x: portfolio.history.map((row) => row.snapshot_date),
                    y: portfolio.history.map((row) => row.plat_value),
                    type: "scatter",
                    mode: "lines+markers",
                    name: "Plat",
                    line: { color: "#22d3ee", width: 2 },
                    marker: { color: "#22d3ee", size: 6 },
                    yaxis: "y"
                  },
                  {
                    x: portfolio.history.map((row) => row.snapshot_date),
                    y: portfolio.history.map((row) => row.vaulted_parts),
                    type: "scatter",
                    mode: "lines+markers",
                    name: "Vaulted Parts",
                    line: { color: "#fbbf24", width: 2 },
                    marker: { color: "#fbbf24", size: 6 },
                    yaxis: "y2"
                  },
                  {
                    x: portfolio.history.map((row) => row.snapshot_date),
                    y: portfolio.history.map((row) => row.unused_vaulted_parts),
                    type: "scatter",
                    mode: "lines+markers",
                    name: "Unused Vaulted",
                    line: { color: "#a78bfa", width: 2 },
                    marker: { color: "#a78bfa", size: 6 },
                    yaxis: "y2"
                  }
                ]}
                layout={{
                  autosize: true,
                  height: 280,
                  margin: { l: 54, r: 54, t: 18, b: 42 },
                  paper_bgcolor: "rgba(0,0,0,0)",
                  plot_bgcolor: "rgba(15,23,42,0.35)",
                  font: { color: "#e2e8f0", size: 12 },
                  legend: { orientation: "h", x: 0, y: 1.14 },
                  xaxis: { type: "category", gridcolor: "#1e293b", tickfont: { color: "#cbd5e1" } },
                  yaxis: { title: { text: "Plat" }, tickformat: "d", nticks: 6, gridcolor: "#1e293b", tickfont: { color: "#cbd5e1" } },
                  yaxis2: {
                    title: { text: "Vaulted Parts" },
                    overlaying: "y",
                    side: "right",
                    tickformat: "d",
                    nticks: 6,
                    gridcolor: "#1e293b",
                    tickfont: { color: "#cbd5e1" }
                  }
                }}
                config={{ displayModeBar: false, responsive: true }}
                className="h-[280px] w-full"
                style={{ width: "100%" }}
              />
            </div>
            <div className="overflow-x-auto border border-slate-800">
              <table className="w-full min-w-[620px] text-sm">
                <thead className="bg-slate-900 text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Day</th>
                    <th className="px-3 py-2 text-right font-medium">Plat</th>
                    <th className="px-3 py-2 text-right font-medium">Platinum</th>
                    <th className="px-3 py-2 text-right font-medium">Vaulted Parts</th>
                    <th className="px-3 py-2 text-right font-medium">Unused Vaulted</th>
                    <th className="px-3 py-2 text-right font-medium">Created Items</th>
                    <th className="px-3 py-2 text-right font-medium">Created Parts</th>
                    <th className="px-3 py-2 text-right font-medium">Unused Parts</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.history.slice(-7).reverse().map((row) => (
                    <tr key={row.snapshot_date} className="border-t border-slate-800">
                      <td className="px-3 py-2 text-slate-300">{formatDay(row.snapshot_date)}</td>
                      <td className="px-3 py-2 text-right font-semibold">{formatPlat(row.plat_value)}</td>
                      <td className="px-3 py-2 text-right font-semibold">{formatPlat(row.platinum_balance)}</td>
                      <td className="px-3 py-2 text-right font-semibold">{row.vaulted_parts}</td>
                      <td className="px-3 py-2 text-right font-semibold">{row.unused_vaulted_parts}</td>
                      <td className="px-3 py-2 text-right">{row.created_prime_items}</td>
                      <td className="px-3 py-2 text-right">{row.created_prime_parts}</td>
                      <td className="px-3 py-2 text-right">{row.unused_prime_parts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-400">Loading portfolio history</div>
        )}
      </section>

      <section className="border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 font-semibold">Collection Status</div>
        <div className="overflow-x-auto border border-slate-800">
          <table className="w-full min-w-[720px] table-fixed text-sm">
            <thead className="bg-slate-900 text-slate-300">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                {collectionColumns.map((column) => (
                  <th key={column.key} className="px-3 py-2 text-right font-medium">{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.collection_status.map((row) => {
                const key = rowKey(row.label);
                return (
                  <tr key={row.label} className="border-t border-slate-800">
                    <td className="px-3 py-2 text-slate-300">{row.label}</td>
                    {collectionColumns.map((column) => {
                      const value = row[column.key];
                      const active = selectedCell?.row === key && selectedCell?.column === column.key;
                      return (
                        <td key={column.key} className="px-2 py-1 text-right">
                          <button
                            type="button"
                            onClick={() => openCollectionCell(key, column.key)}
                            className={`w-full px-2 py-1 text-right font-semibold hover:bg-slate-800 focus:outline-none focus:ring-1 focus:ring-cyan-400 ${active ? "bg-cyan-950 text-cyan-200" : ""}`}
                          >
                            {value}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {(detail || detailLoading || detailError) && (
          <div className="mt-4 border border-slate-800 bg-slate-900/60 p-3">
            {detailLoading && <div className="text-sm text-slate-300">Loading selected items</div>}
            {detailError && <div className="text-sm text-red-300">{detailError}</div>}
            {detail && !detailLoading && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm text-slate-400">Selected Cell</div>
                    <div className="font-semibold">{detail.label}</div>
                  </div>
                  <div className="text-sm text-slate-400">{detail.items.length} item rows</div>
                </div>

                {detail.column === "complete_sets" ? (
                  <>
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="border border-slate-800 bg-slate-950 p-3">
                      <div className="text-sm text-slate-400">Parts Value Total</div>
                      <div className="text-xl font-semibold">{formatPlat(detail.complete_part_value_total)}</div>
                    </div>
                    <div className="border border-slate-800 bg-slate-950 p-3">
                      <div className="text-sm text-slate-400">Full Set Market Total</div>
                      <div className="text-xl font-semibold">{formatPlat(detail.complete_set_market_value_total)}</div>
                    </div>
                    <div className="border border-slate-800 bg-slate-950 p-3">
                      <div className="text-sm text-slate-400">Non-Complete Sets</div>
                      <div className="text-sm text-slate-200">
                        1: {detail.non_complete_missing_one_part} / 2: {detail.non_complete_missing_two_parts} / 3: {detail.non_complete_missing_three_parts} / 4+: {detail.non_complete_missing_four_plus_parts}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm text-slate-400">{selectedCompleteCount} selected</div>
                    <CopyChunks text={selectedSetCopyText} label="Copy Selected" options={copyOptions} />
                  </div>
                  </>
                ) : (
                  <div className="space-y-2">
                    {isOwnedMissingDetail && (
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-sm text-slate-400">{selectedTradableCount} selected tradable rows</div>
                        <input
                          readOnly
                          value={selectedTradableCopyText}
                          className="min-w-[260px] flex-1 border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                        />
                        <CopyChunks text={selectedTradableCopyText} label="Copy Selected" options={copyOptions} />
                      </div>
                    )}
                    <div className="flex gap-2">
                      <input
                        readOnly
                        value={detailCopyText}
                        className="min-w-0 flex-1 border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                      />
                      <CopyChunks text={detailCopyText} options={copyOptions} />
                    </div>
                  </div>
                )}

                <div className="max-h-[360px] overflow-auto border border-slate-800">
                  <table className="w-full min-w-[920px] table-fixed text-sm">
                    <thead className="bg-slate-950 text-slate-300">
                      <tr>
                        {detail.column === "complete_sets" && <th className="w-10 px-2 py-2 text-left font-medium">Sel</th>}
                        {isOwnedMissingDetail && <th className="w-10 px-2 py-2 text-left font-medium">Sel</th>}
                        <th className={detail.column === "complete_sets" ? "w-48 px-2 py-2 text-left font-medium" : "w-2/5 px-3 py-2 text-left font-medium"}>Item</th>
                        <th className={detail.column === "complete_sets" ? "w-14 px-2 py-2 text-left font-medium" : "w-20 px-3 py-2 text-left font-medium"}>Vault</th>
                        <th className={detail.column === "complete_sets" ? "w-14 px-2 py-2 text-right font-medium" : "w-24 px-3 py-2 text-right font-medium"}>Sets</th>
                        {detail.column === "complete_sets" ? (
                          <>
                            <th className="w-16 px-2 py-2 text-right font-medium">Parts Ea</th>
                            <th className="w-16 px-2 py-2 text-right font-medium">Set Ea</th>
                            <th className="w-16 px-2 py-2 text-right font-medium">Parts Tot</th>
                            <th className="w-16 px-2 py-2 text-right font-medium">Set Tot</th>
                            <th className="w-14 px-2 py-2 text-right font-medium">Miss 1</th>
                            <th className="w-14 px-2 py-2 text-right font-medium">Miss 2</th>
                            <th className="w-14 px-2 py-2 text-right font-medium">Miss 3</th>
                            <th className="w-14 px-2 py-2 text-right font-medium">Miss 4+</th>
                          </>
                        ) : (
                          <>
                            {isOwnedMissingDetail && <th className="px-3 py-2 text-left font-medium">Tradable Parts</th>}
                            <th className="px-3 py-2 text-left font-medium">Missing Parts</th>
                          </>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.items.map((item, index) => (
                        <tr key={`${item.item_name}-${index}`} className="border-t border-slate-800">
                          {detail.column === "complete_sets" && (
                            <td className="px-2 py-2">
                              <input
                                type="checkbox"
                                checked={selectedCompleteItems.has(item.item_name)}
                                onChange={(event) => {
                                  const next = new Set(selectedCompleteItems);
                                  if (event.currentTarget.checked) next.add(item.item_name);
                                  else next.delete(item.item_name);
                                  setSelectedCompleteItems(next);
                                }}
                                disabled={item.set_market_value_each <= 0}
                              />
                            </td>
                          )}
                          {isOwnedMissingDetail && (
                            <td className="px-2 py-2">
                              <input
                                type="checkbox"
                                checked={selectedTradableRows.has(detailRowKey(item.item_name, index))}
                                onChange={(event) => {
                                  const next = new Set(selectedTradableRows);
                                  const key = detailRowKey(item.item_name, index);
                                  if (event.currentTarget.checked) next.add(key);
                                  else next.delete(key);
                                  setSelectedTradableRows(next);
                                }}
                                disabled={item.tradable_parts.length === 0}
                              />
                            </td>
                          )}
                          <td className={detail.column === "complete_sets" ? "px-2 py-2 text-slate-100" : "px-3 py-2 text-slate-100"}>
                            {detail.column === "complete_sets" ? (
                              <button
                                type="button"
                                onClick={() => copySetListing(item.item_name, item.set_market_value_each, settings)}
                                disabled={item.set_market_value_each <= 0}
                                className="text-left font-semibold hover:text-cyan-200 disabled:text-slate-500"
                              >
                                {item.item_name}
                              </button>
                            ) : (
                              item.item_name
                            )}
                          </td>
                          <td className={detail.column === "complete_sets" ? "px-2 py-2 text-slate-300" : "px-3 py-2 text-slate-300"}>
                            {item.vaulted ? "Yes" : "No"}
                          </td>
                          <td className={detail.column === "complete_sets" ? "px-2 py-2 text-right font-semibold" : "px-3 py-2 text-right font-semibold"}>{item.set_count}</td>
                          {detail.column === "complete_sets" ? (
                            <>
                              <td className="px-2 py-2 text-right text-slate-300">{formatPlat(item.part_value_each)}</td>
                              <td className="px-2 py-2 text-right text-slate-300">{formatPlat(item.set_market_value_each)}</td>
                              <td className="px-2 py-2 text-right text-slate-300">{formatPlat(item.part_value_total)}</td>
                              <td className="px-2 py-2 text-right text-slate-300">{formatPlat(item.set_market_value_total)}</td>
                              <CopyBucketCell count={item.non_complete_missing_one_part} text={item.missing_one_part_copy_text} copyOptions={copyOptions} />
                              <CopyBucketCell count={item.non_complete_missing_two_parts} text={item.missing_two_parts_copy_text} copyOptions={copyOptions} />
                              <CopyBucketCell count={item.non_complete_missing_three_parts} text={item.missing_three_parts_copy_text} copyOptions={copyOptions} />
                              <CopyBucketCell count={item.non_complete_missing_four_plus_parts} text={item.missing_four_plus_parts_copy_text} copyOptions={copyOptions} />
                            </>
                          ) : (
                            <>
                              {isOwnedMissingDetail && (
                                <td className="px-3 py-2 text-slate-300">
                                  {item.tradable_parts.length > 0
                                    ? item.tradable_parts.map((part) => `${part.name}${part.quantity > 1 ? ` x${part.quantity}` : ""}`).join(", ")
                                    : "None"}
                                </td>
                              )}
                              <td className="px-3 py-2 text-slate-300">
                                {item.missing_parts.length > 0
                                  ? item.missing_parts.map((part) => `${part.name}${part.quantity > 1 ? ` x${part.quantity}` : ""}`).join(", ")
                                  : "None"}
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                      {detail.items.length === 0 && (
                        <tr>
                          <td colSpan={detail.column === "complete_sets" ? 12 : isOwnedMissingDetail ? 6 : 4} className="px-3 py-3 text-center text-slate-400">No items in this cell</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 font-semibold">Trading Position</div>
        <div className="overflow-x-auto border border-slate-800">
          <table className="w-full min-w-[760px] table-fixed text-sm">
            <thead className="bg-slate-900 text-slate-300">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Vaulted Parts</th>
                <th className="px-3 py-2 text-right font-medium">Vaulted Plat</th>
                <th className="px-3 py-2 text-right font-medium">Not Vaulted Parts</th>
                <th className="px-3 py-2 text-right font-medium">Not Vaulted Plat</th>
                <th className="px-3 py-2 text-right font-medium">Total Parts</th>
                <th className="px-3 py-2 text-right font-medium">Total Plat</th>
              </tr>
            </thead>
            <tbody>
              {data.trading_position.map((row) => {
                const isPosition = row.label === "Position";
                const isCoverage = row.label === "Coverage";
                const link = (vaulted: "vaulted" | "not_vaulted" | "total") => isCoverage ? undefined : tradingLink(row.label, vaulted);
                return (
                  <tr key={row.label} className="border-t border-slate-800">
                    <td className="px-3 py-2 text-slate-300">{row.label}</td>
                    <TradingCell to={link("vaulted")} className={`px-3 py-2 text-right font-semibold ${isPosition ? positionClass(row.vaulted.parts) : ""}`}>{isCoverage ? formatPercent(row.vaulted.parts) : row.vaulted.parts}</TradingCell>
                    <TradingCell to={link("vaulted")} className={`px-3 py-2 text-right font-semibold ${isPosition ? positionClass(row.vaulted.plat) : ""}`}>{isCoverage ? formatPercent(row.vaulted.plat) : formatPlat(row.vaulted.plat)}</TradingCell>
                    <TradingCell to={link("not_vaulted")} className={`px-3 py-2 text-right font-semibold ${isPosition ? positionClass(row.not_vaulted.parts) : ""}`}>{isCoverage ? formatPercent(row.not_vaulted.parts) : row.not_vaulted.parts}</TradingCell>
                    <TradingCell to={link("not_vaulted")} className={`px-3 py-2 text-right font-semibold ${isPosition ? positionClass(row.not_vaulted.plat) : ""}`}>{isCoverage ? formatPercent(row.not_vaulted.plat) : formatPlat(row.not_vaulted.plat)}</TradingCell>
                    <TradingCell to={link("total")} className={`px-3 py-2 text-right font-semibold ${isPosition ? positionClass(row.total.parts) : ""}`}>{isCoverage ? formatPercent(row.total.parts) : row.total.parts}</TradingCell>
                    <TradingCell to={link("total")} className={`px-3 py-2 text-right font-semibold ${isPosition ? positionClass(row.total.plat) : ""}`}>{isCoverage ? formatPercent(row.total.plat) : formatPlat(row.total.plat)}</TradingCell>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
