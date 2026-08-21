export const itemTypes = ["All", "Warframe", "Primary", "Secondary", "Melee", "Wing", "Companion", "Other"] as const;

export function ItemTypeFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-slate-400">Type</span>
      <div className="flex flex-wrap border border-slate-700 bg-slate-950">
        {itemTypes.map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => onChange(type)}
            className={`px-3 py-2 font-semibold ${value === type ? "bg-cyan-700 text-white" : "text-slate-300 hover:bg-slate-800"}`}
          >
            {type}
          </button>
        ))}
      </div>
    </div>
  );
}

export function matchesItemType(rowType: string, selectedType: string) {
  return selectedType === "All" || rowType === selectedType;
}
