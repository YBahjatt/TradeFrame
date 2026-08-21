import { ColumnDef } from "@tanstack/react-table";
import { Recommendation, api } from "../api";
import { DataTable } from "../components/DataTable";
import { useAsync } from "../components/useAsync";

const columns: ColumnDef<Recommendation>[] = [
  { accessorKey: "give", header: "Give" },
  { accessorKey: "receive", header: "Receive" },
  { accessorKey: "collection_gain_score", header: "Gain" },
  { accessorKey: "market_delta", header: "Market Delta" },
  { accessorKey: "reason", header: "Reason" }
];

export function OptimizerPage() {
  const { data, error, loading } = useAsync(api.recommendations);
  if (loading) return <div>Loading</div>;
  if (error) return <div className="text-red-300">{error}</div>;
  return <DataTable data={data ?? []} columns={columns} searchPlaceholder="Search recommendations" />;
}
