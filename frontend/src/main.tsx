import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { App } from "./App";
import "./styles.css";
import { DashboardPage } from "./pages/Dashboard";
import { DuplicatesPage } from "./pages/Duplicates";
import { InventoryPage } from "./pages/Inventory";
import { MissingPage } from "./pages/Missing";
import { TradesPage } from "./pages/Trades";
import { StrategicAssetsPage } from "./pages/StrategicAssets";
import { PublishedPage } from "./pages/Published";
import { SettingsPage } from "./pages/Settings";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "inventory", element: <InventoryPage /> },
      { path: "missing", element: <MissingPage /> },
      { path: "tradable", element: <DuplicatesPage /> },
      { path: "published", element: <PublishedPage /> },
      { path: "strategic-assets", element: <StrategicAssetsPage /> },
      { path: "duplicates", element: <DuplicatesPage /> },
      { path: "trades", element: <TradesPage /> },
      { path: "settings", element: <SettingsPage /> }
    ]
  }
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
