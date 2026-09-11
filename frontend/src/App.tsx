import { NavLink, Outlet } from "react-router-dom";
import { api } from "./api";
import { useState } from "react";

const links = [
  ["Dashboard", "/"],
  ["Inventory", "/inventory"],
  ["Missing", "/missing"],
  ["Tradable", "/tradable"],
  ["Published", "/published"],
  ["Market Matches", "/market-matches"],
  ["Strategic Assets", "/strategic-assets"],
  ["Trades", "/trades"],
  ["Settings", "/settings"]
];

export function App() {
  const [syncStatus, setSyncStatus] = useState("");
  const runSync = async () => {
    setSyncStatus("Syncing");
    try {
      const result = await api.sync();
      setSyncStatus(result.message);
    } catch (error) {
      setSyncStatus(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-950">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-5 py-3">
          <div className="text-lg font-semibold">TradeFrame</div>
          <nav className="flex flex-1 gap-1">
            {links.map(([label, to]) => (
              <NavLink key={to} to={to} className={({ isActive }) => `px-3 py-2 text-sm ${isActive ? "bg-cyan-700" : "hover:bg-slate-800"}`}>
                {label}
              </NavLink>
            ))}
          </nav>
          <button className="border border-cyan-500 px-3 py-2 text-sm hover:bg-cyan-900" onClick={runSync}>
            Sync
          </button>
        </div>
        {syncStatus && <div className="mx-auto max-w-7xl px-5 pb-3 text-sm text-cyan-200">{syncStatus}</div>}
      </header>
      <main className="mx-auto max-w-7xl px-5 py-5">
        <Outlet />
      </main>
    </div>
  );
}
