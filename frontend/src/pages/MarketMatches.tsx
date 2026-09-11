import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { MarketMatchItem, MarketMatchResponse, api } from "../api";
import { copyText } from "../components/CopyChunks";

const missingBuckets = [
  { value: 1, label: "Missing 1" },
  { value: 2, label: "Missing 2" },
  { value: 3, label: "Missing 3" },
  { value: 4, label: "Missing 4+" }
];

function itemList(items: MarketMatchItem[]) {
  return items.map((item) => `${item.chat_text}${item.platinum > 0 ? ` ${item.platinum.toFixed(0)}p` : ""}`).join(" ");
}

function statusText(status?: string | null, lastSeen?: string | null, reputation?: number | null) {
  const parts = [status ?? "unknown"];
  if (lastSeen) parts.push(`seen ${new Date(lastSeen).toLocaleString()}`);
  if (reputation !== null && reputation !== undefined) parts.push(`rep ${reputation}`);
  return parts.join(" / ");
}

export function MarketMatchesPage() {
  const [data, setData] = useState<MarketMatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanOwnedMissing, setScanOwnedMissing] = useState<number[]>([]);
  const [scanNotMissing, setScanNotMissing] = useState<number[]>([]);
  const [scanDirty, setScanDirty] = useState(false);
  const [visibleOwnedMissing, setVisibleOwnedMissing] = useState<number[]>([]);
  const [visibleNotMissing, setVisibleNotMissing] = useState<number[]>([]);

  async function load(refresh = false, applyScanScope = false, statusRefresh = false) {
    setLoading(true);
    setError(null);
    try {
      const result = await api.marketMatches(refresh, { ownedMissing: scanOwnedMissing, notMissing: scanNotMissing }, applyScanScope, statusRefresh);
      setData(result);
      if (applyScanScope || !scanDirty) {
        setScanOwnedMissing(result.scan_owned_missing);
        setScanNotMissing(result.scan_not_missing);
        setScanDirty(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function toggleValues(setter: Dispatch<SetStateAction<number[]>>, value: number) {
    setter((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value].sort((left, right) => left - right));
  }

  function toggleScanValues(setter: Dispatch<SetStateAction<number[]>>, value: number) {
    setScanDirty(true);
    toggleValues(setter, value);
  }

  useEffect(() => {
    load(false, false, true);
  }, []);

  useEffect(() => {
    if (!data?.refreshing) return;
    const timer = window.setTimeout(() => load(), 10000);
    return () => window.clearTimeout(timer);
  }, [data?.refreshing]);

  const generatedAt = data?.generated_at ? new Date(data.generated_at).toLocaleString() : "No completed scan yet";
  const visibleTags = useMemo(() => new Set([
    ...visibleOwnedMissing.map((bucket) => `owned_mastered:${bucket}`),
    ...visibleNotMissing.map((bucket) => `not:${bucket}`)
  ]), [visibleOwnedMissing, visibleNotMissing]);
  const shownMatches = useMemo(() => {
    if (!data) return [];
    if (visibleTags.size === 0) return data.matches;
    return data.matches.filter((match) => match.they_sell.some((item) => item.lead_tags.some((tag) => visibleTags.has(tag))));
  }, [data, visibleTags]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Market Matches</h1>
          <div className="text-sm text-slate-400">Read-only Warframe Market matches where they sell parts you need and buy parts you can spare.</div>
        </div>
      </div>

      {(loading || data?.refreshing) && <div className="text-cyan-200">Refreshing market data in the background</div>}
      {error && <div className="text-red-300">{error}</div>}
      {data && (
        <>
          <section className="grid gap-3 border border-slate-800 bg-slate-950 p-3 md:grid-cols-2">
            <div>
              <div className="mb-2 text-sm font-semibold text-slate-300">Backend Scan Scope: Owned/Mastered</div>
              <div className="grid grid-cols-2 gap-2">
                {missingBuckets.map((bucket) => (
                  <label key={`scan-owned-${bucket.value}`} className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={scanOwnedMissing.includes(bucket.value)}
                      onChange={() => toggleScanValues(setScanOwnedMissing, bucket.value)}
                    />
                    {bucket.label}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-semibold text-slate-300">Backend Scan Scope: Not Built</div>
              <div className="grid grid-cols-2 gap-2">
                {missingBuckets.map((bucket) => (
                  <label key={`scan-not-${bucket.value}`} className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={scanNotMissing.includes(bucket.value)}
                      onChange={() => toggleScanValues(setScanNotMissing, bucket.value)}
                    />
                    {bucket.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="md:col-span-2">
              <button type="button" onClick={() => load(true, true)} className="border border-cyan-500 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-950">
                Apply Scan Scope
              </button>
              {scanDirty && <span className="ml-3 text-sm text-amber-200">Unsaved scan scope</span>}
            </div>
          </section>

          <section className="grid gap-3 border border-slate-800 bg-slate-950 p-3 md:grid-cols-2">
            <div>
              <div className="mb-2 text-sm font-semibold text-slate-300">Visible Lead Filter: Owned/Mastered</div>
              <div className="grid grid-cols-2 gap-2">
                {missingBuckets.map((bucket) => (
                  <label key={`visible-owned-${bucket.value}`} className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={visibleOwnedMissing.includes(bucket.value)}
                      onChange={() => toggleValues(setVisibleOwnedMissing, bucket.value)}
                    />
                    {bucket.label}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-semibold text-slate-300">Visible Lead Filter: Not Built</div>
              <div className="grid grid-cols-2 gap-2">
                {missingBuckets.map((bucket) => (
                  <label key={`visible-not-${bucket.value}`} className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={visibleNotMissing.includes(bucket.value)}
                      onChange={() => toggleValues(setVisibleNotMissing, bucket.value)}
                    />
                    {bucket.label}
                  </label>
                ))}
              </div>
            </div>
          </section>

          <section className="grid gap-3 md:grid-cols-4">
            <div className="border border-slate-800 bg-slate-950 p-3">
              <div className="text-sm text-slate-400">Matches</div>
              <div className="text-2xl font-semibold">{shownMatches.length}</div>
              <div className="text-xs text-slate-500">{data.matches.length} local leads after inventory sync</div>
            </div>
            <div className="border border-slate-800 bg-slate-950 p-3">
              <div className="text-sm text-slate-400">Missing Part Types Checked</div>
              <div className="text-2xl font-semibold">
                {data.missing_items_checked}{data.missing_part_types_total > 0 ? ` / ${data.missing_part_types_total}` : ""}
              </div>
              <div className="text-xs text-slate-500">
                {data.missing_part_quantity_checked}{data.missing_part_quantity_total > 0 ? ` / ${data.missing_part_quantity_total}` : ""} total parts
              </div>
            </div>
            <div className="border border-slate-800 bg-slate-950 p-3">
              <div className="text-sm text-slate-400">Market Users Checked</div>
              <div className="text-2xl font-semibold">{data.users_checked}</div>
            </div>
            <div className="border border-slate-800 bg-slate-950 p-3">
              <div className="text-sm text-slate-400">Last Updated</div>
              <div className="text-sm font-semibold">{generatedAt}</div>
            </div>
          </section>

          <div className="space-y-3">
            {shownMatches.map((match) => (
              <section key={match.user_slug} className="border border-slate-800 bg-slate-950 p-3">
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold">{match.user_name}</div>
                    <div className="text-xs text-slate-500">
                      {statusText(match.status, match.last_seen, match.reputation)}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {match.copy_texts.map((text, index) => (
                      <button
                        key={`${match.user_slug}-${index}`}
                        type="button"
                        onClick={() => copyText(text)}
                        className="border border-cyan-500 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-950"
                      >
                        Copy {match.copy_texts.length > 1 ? index + 1 : ""}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  <div>
                    <div className="mb-1 text-sm font-semibold text-cyan-200">They Sell / You Need</div>
                    <div className="border border-slate-800 bg-slate-900/40 p-2 text-sm">{itemList(match.they_sell)}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-sm font-semibold text-amber-200">They Buy / You Have</div>
                    <div className="border border-slate-800 bg-slate-900/40 p-2 text-sm">{itemList(match.they_buy)}</div>
                  </div>
                </div>
                <div className="mt-3 space-y-1">
                  {match.copy_texts.map((text, index) => (
                    <div key={`${match.user_slug}-text-${index}`} className="overflow-hidden text-ellipsis whitespace-nowrap border border-slate-800 bg-slate-900/40 px-2 py-1 text-xs text-slate-400">
                      {text}
                    </div>
                  ))}
                </div>
              </section>
            ))}
            {shownMatches.length === 0 && !data.refreshing && data.generated_at && <div className="border border-slate-800 bg-slate-950 p-4 text-center text-slate-400">No mutual market matches found.</div>}
            {shownMatches.length === 0 && data.refreshing && !data.generated_at && <div className="border border-slate-800 bg-slate-950 p-4 text-center text-slate-400">First market scan is still running.</div>}
          </div>

          {data.errors.length > 0 && (
            <section className="border border-slate-800 bg-slate-950 p-3">
              <div className="mb-2 font-semibold">Market Lookup Notes</div>
              <div className="space-y-1 text-xs text-slate-400">
                {data.errors.map((line) => <div key={line}>{line}</div>)}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
