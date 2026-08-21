import { useMemo, useState } from "react";

import { api } from "../api";
import { ItemTypeFilter, matchesItemType } from "../components/ItemTypeFilter";
import { useAsync } from "../components/useAsync";

type SortMode = "score" | "missing" | "name";

const sortOptions: Array<{ value: SortMode; label: string }> = [
  { value: "score", label: "Score" },
  { value: "missing", label: "Missing Parts" },
  { value: "name", label: "Name" }
];

function formatChatPart(name: string) {
  if (name.endsWith(" Blueprint")) return `[${name.slice(0, -10)}] BP`;
  return `[${name}]`;
}

export function MissingPage() {
  const { data, error, loading } = useAsync(api.missing);
  const [sortMode, setSortMode] = useState<SortMode>("score");
  const [search, setSearch] = useState("");
  const [itemType, setItemType] = useState("All");

  const sortedItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    const items = [...(data ?? [])].filter((item) => matchesItemType(item.item_type, itemType)).filter((item) => {
      return !query || item.name.toLowerCase().includes(query) || item.missing_parts.some((part) => part.toLowerCase().includes(query));
    });
    return items.sort((left, right) => {
      if (sortMode === "name") return left.name.localeCompare(right.name);
      if (sortMode === "missing") {
        return left.missing_parts.length - right.missing_parts.length || left.name.localeCompare(right.name);
      }
      return right.collection_gain_score - left.collection_gain_score || left.missing_parts.length - right.missing_parts.length || left.name.localeCompare(right.name);
    });
  }, [data, itemType, search, sortMode]);

  if (loading) return <div>Loading</div>;
  if (error) return <div className="text-red-300">{error}</div>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-400">{sortedItems.length} missing items</div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-400">Sort</span>
          <div className="flex border border-slate-700 bg-slate-950">
            {sortOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setSortMode(option.value)}
                className={`px-3 py-2 font-semibold ${sortMode === option.value ? "bg-cyan-700 text-white" : "text-slate-300 hover:bg-slate-800"}`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <input
        className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search missing items"
      />
      <ItemTypeFilter value={itemType} onChange={setItemType} />

      <div className="overflow-auto border border-slate-800">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-900 text-left">
            <tr>
              <th className="w-28 px-3 py-2">Type</th>
              <th className="px-3 py-2">Item</th>
              <th className="px-3 py-2">Missing Parts</th>
              <th className="px-3 py-2 text-right">Complete</th>
              <th className="px-3 py-2 text-right">Score</th>
            </tr>
          </thead>
          <tbody>
        {sortedItems.map((item) => (
          <tr key={item.name} className="border-t border-slate-800 hover:bg-slate-900/70">
            <td className="whitespace-nowrap px-3 py-2 text-slate-300">{item.item_type}</td>
            <td className="whitespace-nowrap px-3 py-2 font-semibold">{item.name}</td>
            <td className="px-3 py-2 text-slate-300">{item.missing_parts.map(formatChatPart).join(", ")}</td>
            <td className="whitespace-nowrap px-3 py-2 text-right">{item.collection_percent}%</td>
            <td className="whitespace-nowrap px-3 py-2 text-right text-cyan-300">{item.collection_gain_score}</td>
          </tr>
        ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
