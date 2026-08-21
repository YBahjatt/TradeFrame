import { StrategicAssetRow, api } from "../api";
import { CopyChunks, copyText } from "../components/CopyChunks";
import { useAsync } from "../components/useAsync";

function formatPlat(value: number) {
  return `${value.toFixed(0)}p`;
}

function tierClass(tier: string) {
  if (tier === "Junk") return "text-slate-400";
  return tier === "Crown Jewels" ? "text-amber-300" : "text-cyan-300";
}

function copyPartList(rows: StrategicAssetRow[]) {
  return rows.map((row) => row.chat_text).join(", ");
}

function AssetTable({ title, rows, emptyText }: { title: string; rows: StrategicAssetRow[]; emptyText: string }) {
  return (
    <section className="border border-slate-800 bg-slate-950 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="font-semibold">{title}</div>
          <div className="text-xs text-slate-500">{rows.length} parts</div>
        </div>
        <CopyChunks text={copyPartList(rows)} label="Copy All" />
      </div>
      <div className="overflow-auto border border-slate-800">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-slate-900 text-slate-300">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Tier</th>
              <th className="px-3 py-2 text-left font-medium">Part</th>
              <th className="px-3 py-2 text-left font-medium">Item</th>
              <th className="px-3 py-2 text-right font-medium">Qty</th>
              <th className="px-3 py-2 text-right font-medium">Each</th>
              <th className="px-3 py-2 text-right font-medium">Total</th>
              <th className="px-3 py-2 text-right font-medium">Vaulted</th>
              <th className="px-3 py-2 text-left font-medium">WF Chat</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.side}-${row.name}-${row.tier}`} className="border-t border-slate-800">
                <td className={`px-3 py-2 font-semibold ${tierClass(row.tier)}`}>{row.tier}</td>
                <td className="px-3 py-2 font-semibold">{row.name}</td>
                <td className="px-3 py-2 text-slate-300">{row.item_name}</td>
                <td className="px-3 py-2 text-right">{row.quantity}</td>
                <td className="px-3 py-2 text-right font-semibold">{formatPlat(row.market_value)}</td>
                <td className="px-3 py-2 text-right font-semibold">{formatPlat(row.total_value)}</td>
                <td className="px-3 py-2 text-right">{row.vaulted ? "Yes" : "No"}</td>
                <td className="px-3 py-2">
                  <button type="button" onClick={() => copyText(row.chat_text)} className="text-cyan-200 hover:text-cyan-100">
                    {row.chat_text}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="p-4 text-center text-slate-400">{emptyText}</div>}
      </div>
    </section>
  );
}

export function StrategicAssetsPage() {
  const { data, error, loading } = useAsync(api.strategicAssets);

  if (loading) return <div>Loading strategic assets</div>;
  if (error) return <div className="text-red-300">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Strategic Assets</h1>
        <div className="text-sm text-slate-400">Top missing, top tradable, and cheapest tradable Prime parts by current lowest market price.</div>
      </div>

      <section className="grid gap-3 md:grid-cols-3">
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Highest Listed Part</div>
          <div className="text-2xl font-semibold">{formatPlat(data.max_part_value)}</div>
        </div>
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Crown Jewels</div>
          <div className="text-2xl font-semibold text-amber-300">Top 5</div>
          <div className="text-xs text-slate-500">Lowest in tier: {formatPlat(data.crown_min_value)}</div>
        </div>
        <div className="border border-slate-800 bg-slate-950 p-3">
          <div className="text-sm text-slate-400">Strategic</div>
          <div className="text-2xl font-semibold text-cyan-300">Next 15</div>
          <div className="text-xs text-slate-500">Lowest in tier: {formatPlat(data.strategic_min_value)}</div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <AssetTable title="Missing" rows={data.missing} emptyText="No missing priced parts found." />
        <AssetTable title="Tradable" rows={data.owned} emptyText="No tradable priced parts found." />
        <AssetTable title="Junk" rows={data.junk} emptyText="No cheap tradable priced parts found." />
      </div>
    </div>
  );
}
