import { useEffect, useMemo, useState } from "react";

import { TradablePartRow, api } from "../api";
import { ItemTypeFilter, matchesItemType } from "../components/ItemTypeFilter";
import { useAsync } from "../components/useAsync";

type PublishedEntry = {
  published: boolean;
  quantity: number;
  retain: number;
};

type PublishedStore = Record<string, PublishedEntry>;

const STORAGE_KEY = "tradeframe.publishedList.v1";

function loadStore(): PublishedStore {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (!value) return {};
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveStore(store: PublishedStore) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function cleanQuantity(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.floor(value));
}

function publishedQuantity(row: TradablePartRow, store: PublishedStore) {
  const entry = store[row.unique_name];
  if (!entry?.published) return 0;
  const availableAboveRetain = Math.max(0, row.quantity - cleanQuantity(entry.retain));
  return Math.min(cleanQuantity(entry.quantity), availableAboveRetain);
}

export function PublishedPage() {
  const loader = useMemo(() => () => api.tradable("tradable"), []);
  const { data, error, loading } = useAsync(loader);
  const [store, setStore] = useState<PublishedStore>(() => loadStore());
  const [search, setSearch] = useState("");
  const [itemType, setItemType] = useState("All");
  const [bulkQuantity, setBulkQuantity] = useState("1");
  const [bulkRetain, setBulkRetain] = useState("0");

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data ?? [])
      .filter((row) => matchesItemType(row.item_type, itemType))
      .filter((row) => !query || row.name.toLowerCase().includes(query) || row.item_name.toLowerCase().includes(query))
      .sort((left, right) => {
        return left.item_type.localeCompare(right.item_type) || left.item_name.localeCompare(right.item_name) || left.name.localeCompare(right.name);
      });
  }, [data, itemType, search]);

  const groupRows = useMemo(() => {
    const counts = new Map<string, number>();
    const firstIds = new Set<string>();
    const seen = new Set<string>();
    for (const row of rows) {
      const key = `${row.item_type}\u0000${row.item_name}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
      if (!seen.has(key)) {
        seen.add(key);
        firstIds.add(`${key}\u0000${row.unique_name}`);
      }
    }
    return { counts, firstIds };
  }, [rows]);

  useEffect(() => {
    if (!data) return;
    const tradableById = new Map(data.map((row) => [row.unique_name, row.quantity]));
    let changed = false;
    const next: PublishedStore = {};
    for (const [id, entry] of Object.entries(store)) {
      const max = tradableById.get(id);
      if (!max) {
        changed = true;
        continue;
      }
      const quantity = cleanQuantity(entry.quantity);
      const retain = cleanQuantity(entry.retain);
      const published = Boolean(entry.published) && quantity > 0;
      next[id] = { published, quantity, retain };
      changed = changed || published !== entry.published || quantity !== entry.quantity || retain !== entry.retain;
    }
    if (changed) {
      setStore(next);
      saveStore(next);
    }
  }, [data]);

  function updateEntry(row: TradablePartRow, patch: Partial<PublishedEntry>) {
    setStore((current) => {
      const existing = current[row.unique_name] ?? { published: false, quantity: Math.min(1, row.quantity), retain: 0 };
      const quantity = cleanQuantity(patch.quantity ?? existing.quantity);
      const retain = cleanQuantity(patch.retain ?? existing.retain);
      const published = Boolean(patch.published ?? existing.published) && quantity > 0;
      const next = { ...current, [row.unique_name]: { published, quantity, retain } };
      saveStore(next);
      return next;
    });
  }

  function updateVisibleRows(published: boolean, quantity?: number, retain?: number) {
    setStore((current) => {
      const next = { ...current };
      for (const row of rows) {
        const existing = next[row.unique_name] ?? { published: false, quantity: Math.min(1, row.quantity), retain: 0 };
        const nextQuantity = cleanQuantity(quantity ?? existing.quantity);
        const nextRetain = cleanQuantity(retain ?? existing.retain);
        next[row.unique_name] = { published: published && nextQuantity > 0, quantity: nextQuantity, retain: nextRetain };
      }
      saveStore(next);
      return next;
    });
  }

  function applyBulkQuantity(value: string) {
    setBulkQuantity(value);
    const quantity = cleanQuantity(Number(value));
    if (quantity <= 0) return;
    updateVisibleRows(true, quantity);
  }

  function applyBulkRetain(value: string) {
    setBulkRetain(value);
    const retain = cleanQuantity(Number(value));
    updateVisibleRows(true, undefined, retain);
  }

  const publishedRows = (data ?? []).filter((row) => publishedQuantity(row, store) > 0);
  const publishedParts = publishedRows.reduce((sum, row) => sum + publishedQuantity(row, store), 0);
  const allVisiblePublished = rows.length > 0 && rows.every((row) => publishedQuantity(row, store) > 0);

  if (loading) return <div>Loading</div>;
  if (error) return <div className="text-red-300">{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Published List</h1>
          <div className="text-sm text-slate-400">Only checked rows and quantities on this screen are eligible to be shared later.</div>
        </div>
        <div className="text-right text-sm text-slate-300">
          <div>{publishedRows.length} published part types</div>
          <div>{publishedParts} published parts</div>
        </div>
      </div>

      <input
        className="w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
        placeholder="Search tradable parts"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      <ItemTypeFilter value={itemType} onChange={setItemType} />

      <div className="overflow-auto border border-slate-800">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-900 text-left">
            <tr>
              <th className="w-28 px-3 py-2">Type</th>
              <th className="px-3 py-2">Item</th>
              <th className="w-20 px-3 py-2">
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={allVisiblePublished} onChange={(event) => updateVisibleRows(event.target.checked)} />
                  <span>Publish</span>
                </div>
              </th>
              <th className="px-3 py-2">Part</th>
              <th className="w-28 px-3 py-2 text-right">Tradable</th>
              <th className="w-32 px-3 py-2 text-right">
                <div className="flex items-center justify-end gap-2">
                  <span>Retain</span>
                  <input
                    className="w-16 border border-slate-700 bg-slate-950 px-2 py-1 text-right"
                    type="number"
                    min={0}
                    value={bulkRetain}
                    onChange={(event) => applyBulkRetain(event.target.value)}
                  />
                </div>
              </th>
              <th className="w-32 px-3 py-2 text-right">Published Now</th>
              <th className="w-36 px-3 py-2 text-right">
                <div className="flex items-center justify-end gap-2">
                  <span>Max Qty</span>
                  <input
                    className="w-16 border border-slate-700 bg-slate-950 px-2 py-1 text-right"
                    type="number"
                    min={0}
                    value={bulkQuantity}
                    onChange={(event) => applyBulkQuantity(event.target.value)}
                  />
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const groupKey = `${row.item_type}\u0000${row.item_name}`;
              const isFirstInGroup = groupRows.firstIds.has(`${groupKey}\u0000${row.unique_name}`);
              const entry = store[row.unique_name] ?? { published: false, quantity: Math.min(1, row.quantity), retain: 0 };
              const quantity = cleanQuantity(entry.quantity);
              const retain = cleanQuantity(entry.retain);
              const currentPublished = publishedQuantity(row, store);
              const published = currentPublished > 0;
              return (
                <tr key={row.unique_name} className="border-t border-slate-800">
                  {isFirstInGroup && (
                    <>
                      <td rowSpan={groupRows.counts.get(groupKey)} className="border-t border-slate-800 px-3 py-2 align-top text-slate-300">
                        {row.item_type}
                      </td>
                      <td rowSpan={groupRows.counts.get(groupKey)} className="border-t border-slate-800 px-3 py-2 align-top font-semibold">
                        {row.item_name}
                      </td>
                    </>
                  )}
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={published}
                      onChange={(event) => updateEntry(row, { published: event.target.checked, quantity: quantity || Math.min(1, row.quantity) })}
                    />
                  </td>
                  <td className="px-3 py-2 font-medium">{row.name}</td>
                  <td className="px-3 py-2 text-right">{row.quantity}</td>
                  <td className="px-3 py-2 text-right">
                    <input
                      className="w-20 border border-slate-700 bg-slate-950 px-2 py-1 text-right"
                      type="number"
                      min={0}
                      value={retain}
                      onChange={(event) => updateEntry(row, { retain: Number(event.target.value), published })}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">{currentPublished}</td>
                  <td className="px-3 py-2 text-right">
                    <input
                      className="w-20 border border-slate-700 bg-slate-950 px-2 py-1 text-right"
                      type="number"
                      min={0}
                      value={quantity}
                      onChange={(event) => updateEntry(row, { quantity: Number(event.target.value), published })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
