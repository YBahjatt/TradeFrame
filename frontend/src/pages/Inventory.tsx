import { useMemo, useState } from "react";

import { InventoryRow, api } from "../api";
import { ItemTypeFilter, matchesItemType } from "../components/ItemTypeFilter";
import { useAsync } from "../components/useAsync";

function itemName(row: InventoryRow) {
  return row.parent_name || row.name;
}

function groupMeta(rows: InventoryRow[]) {
  const counts = new Map<string, number>();
  const firstIds = new Set<string>();
  const seen = new Set<string>();
  for (const row of rows) {
    const key = `${row.item_type}\u0000${itemName(row)}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
    if (!seen.has(key)) {
      seen.add(key);
      firstIds.add(`${key}\u0000${row.unique_name}`);
    }
  }
  return { counts, firstIds };
}

export function InventoryPage() {
  const { data, error, loading } = useAsync(api.inventory);
  const [search, setSearch] = useState("");
  const [itemType, setItemType] = useState("All");

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data ?? [])
      .filter((row) => matchesItemType(row.item_type, itemType))
      .filter((row) => !query || row.name.toLowerCase().includes(query) || itemName(row).toLowerCase().includes(query))
      .sort((left, right) => left.item_type.localeCompare(right.item_type) || itemName(left).localeCompare(itemName(right)) || left.name.localeCompare(right.name));
  }, [data, itemType, search]);
  const groups = useMemo(() => groupMeta(rows), [rows]);

  if (loading) return <div>Loading</div>;
  if (error) return <div className="text-red-300">{error}</div>;

  return (
    <div className="space-y-3">
      <input
        className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search Prime parts"
      />
      <ItemTypeFilter value={itemType} onChange={setItemType} />
      <div className="overflow-auto border border-slate-800">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-900 text-left">
            <tr>
              <th className="w-28 px-3 py-2">Type</th>
              <th className="px-3 py-2">Item</th>
              <th className="px-3 py-2">Part</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Vaulted</th>
              <th className="px-3 py-2">Mastered</th>
              <th className="px-3 py-2 text-right">Owned</th>
              <th className="px-3 py-2 text-right">Tradable</th>
              <th className="px-3 py-2 text-right">Safe</th>
              <th className="px-3 py-2 text-right">Market</th>
              <th className="px-3 py-2 text-right">Collection</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const key = `${row.item_type}\u0000${itemName(row)}`;
              const isFirst = groups.firstIds.has(`${key}\u0000${row.unique_name}`);
              return (
                <tr key={row.unique_name} className="border-t border-slate-800 hover:bg-slate-900/70">
                  {isFirst && (
                    <>
                      <td rowSpan={groups.counts.get(key)} className="px-3 py-2 align-top text-slate-300">{row.item_type}</td>
                      <td rowSpan={groups.counts.get(key)} className="px-3 py-2 align-top font-semibold">{itemName(row)}</td>
                    </>
                  )}
                  <td className="whitespace-nowrap px-3 py-2">{row.name}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.category}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.vaulted ? "Yes" : "No"}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.mastered ? "Yes" : "No"}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.owned_count}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.tradable_count}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.safe_to_trade}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.market_value}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.collection_value}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
