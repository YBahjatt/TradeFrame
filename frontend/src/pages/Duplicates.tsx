import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { TradablePartRow, api } from "../api";
import { ItemTypeFilter, matchesItemType } from "../components/ItemTypeFilter";
import { useAsync } from "../components/useAsync";

type SortKey = keyof Pick<TradablePartRow, "item_type" | "item_name" | "name" | "status" | "vaulted" | "quantity" | "market_value" | "total_value" | "owned_count" | "required_count" | "chat_text" | "reason">;
type SortDirection = "asc" | "desc";

function titleFor(status?: string | null, vaulted?: string | null) {
  const statusLabel = status ? status[0].toUpperCase() + status.slice(1) : "Tradable Position";
  const vaultLabel = vaulted === "vaulted" ? "Vaulted" : vaulted === "not_vaulted" ? "Not Vaulted" : "Total";
  return `${statusLabel} / ${vaultLabel}`;
}

function sortValue(row: TradablePartRow, key: SortKey) {
  const value = row[key];
  if (typeof value === "boolean") return value ? 1 : 0;
  return value;
}

function compareRows(left: TradablePartRow, right: TradablePartRow, key: SortKey, direction: SortDirection) {
  const leftValue = sortValue(left, key);
  const rightValue = sortValue(right, key);
  let result = 0;
  if (typeof leftValue === "number" && typeof rightValue === "number") {
    result = leftValue - rightValue;
  } else {
    result = String(leftValue ?? "").localeCompare(String(rightValue ?? ""));
  }
  if (result === 0) {
    result = left.item_type.localeCompare(right.item_type) || left.item_name.localeCompare(right.item_name) || left.name.localeCompare(right.name);
  }
  return direction === "asc" ? result : -result;
}

export function DuplicatesPage() {
  const [params] = useSearchParams();
  const [search, setSearch] = useState("");
  const [itemType, setItemType] = useState("All");
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: "item_name", direction: "asc" });
  const status = params.get("status") ?? "tradable";
  const vaulted = params.get("vaulted") ?? undefined;
  const loader = useMemo(() => () => api.tradable(status, vaulted), [status, vaulted]);
  const { data, error, loading } = useAsync(loader);

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data ?? [])
      .filter((row) => matchesItemType(row.item_type, itemType))
      .filter((row) => !query || row.name.toLowerCase().includes(query) || row.item_name.toLowerCase().includes(query))
      .sort((left, right) => compareRows(left, right, sort.key, sort.direction));
  }, [data, itemType, search, sort]);
  const canMergeItemCells = sort.key === "item_type" || sort.key === "item_name";
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
  const totalParts = rows.reduce((sum, row) => sum + row.quantity, 0);
  const totalPlat = rows.reduce((sum, row) => sum + row.total_value, 0);

  if (loading) return <div>Loading</div>;
  if (error) return <div className="text-red-300">{error}</div>;

  function toggleSort(key: SortKey) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc"
    }));
  }

  function SortHeader({ column, label, align = "left", className = "" }: { column: SortKey; label: string; align?: "left" | "right"; className?: string }) {
    const active = sort.key === column;
    return (
      <th className={`px-3 py-2 ${align === "right" ? "text-right" : "text-left"} ${className}`}>
        <button type="button" onClick={() => toggleSort(column)} className={`font-semibold hover:text-cyan-200 ${active ? "text-cyan-200" : ""}`}>
          {label}{active ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
        </button>
      </th>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Tradable</h1>
          <div className="text-sm text-slate-400">{titleFor(status, vaulted)}</div>
        </div>
        <div className="text-right text-sm text-slate-300">
          <div>{totalParts} parts</div>
          <div>{totalPlat.toFixed(0)}p</div>
        </div>
      </div>
      <input
        className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search tradable parts"
      />
      <ItemTypeFilter value={itemType} onChange={setItemType} />
      <div className="overflow-auto border border-slate-800">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-900 text-left">
            <tr>
              <SortHeader column="item_type" label="Type" className="w-28" />
              <SortHeader column="item_name" label="Item" />
              <SortHeader column="name" label="Part" />
              <SortHeader column="status" label="Status" />
              <SortHeader column="vaulted" label="Vaulted" />
              <SortHeader column="quantity" label="Qty" align="right" />
              <SortHeader column="market_value" label="Each" align="right" />
              <SortHeader column="total_value" label="Total" align="right" />
              <SortHeader column="owned_count" label="Owned" align="right" />
              <SortHeader column="required_count" label="Need" align="right" />
              <SortHeader column="chat_text" label="WF Chat" />
              <SortHeader column="reason" label="Reason" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const groupKey = `${row.item_type}\u0000${row.item_name}`;
              const isFirstInGroup = groupRows.firstIds.has(`${groupKey}\u0000${row.unique_name}`);
              return (
                <tr key={row.unique_name} className="border-t border-slate-800 hover:bg-slate-900/70">
                  {canMergeItemCells && isFirstInGroup && (
                    <>
                      <td rowSpan={groupRows.counts.get(groupKey)} className="px-3 py-2 align-top text-slate-300">{row.item_type}</td>
                      <td rowSpan={groupRows.counts.get(groupKey)} className="px-3 py-2 align-top font-semibold">{row.item_name}</td>
                    </>
                  )}
                  {!canMergeItemCells && (
                    <>
                      <td className="px-3 py-2 align-top text-slate-300">{row.item_type}</td>
                      <td className="px-3 py-2 align-top font-semibold">{row.item_name}</td>
                    </>
                  )}
                  <td className="whitespace-nowrap px-3 py-2">{row.name}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.status}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.vaulted ? "Yes" : "No"}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.quantity}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.market_value}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.total_value}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.owned_count}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">{row.required_count}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.chat_text}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
