# TradeFrame

TradeFrame is a desktop-first analytics tool for Warframe Prime collectors. It helps you understand what you own, what you are missing, what you can safely trade, and which parts you explicitly choose to publish. It can also generate Warframe chat-ready copy chunks so you can quickly share the parts you want to buy or sell without manually formatting long lists.

TradeFrame is an independent fan-made tool and is not affiliated with Digital Extremes, Warframe, Overwolf, or AlecaFrame.

TradeFrame is read-only toward AlecaFrame. It reads AlecaFrame's local data cache and stores its own analytics data in a local SQLite database.

## Run TradeFrame

Use the launcher:

```powershell
.\Start TradeFrame.bat
```

The launcher starts the backend and frontend on stable local ports, preferring:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

If either port is already busy, the launcher chooses the next available port and prints the actual TradeFrame URL.

TradeFrame stores local app data in `data/tradeframe.sqlite3`. This file contains personal inventory and trade data and is intentionally ignored by Git.

## AlecaFrame Data Directory

On first run, TradeFrame tries to detect AlecaFrame's data directory automatically. This is not the folder where AlecaFrame is installed. It is the user data folder that contains AlecaFrame's local files, including `lastData.dat`.

The Settings page shows whether the configured AlecaFrame data directory contains the data TradeFrame needs.

## Architecture

- `backend/`: FastAPI, SQLAlchemy, SQLite, Aleca adapter, services, repositories, tests.
- `frontend/`: React, TypeScript, Vite, TailwindCSS, TanStack Table, Plotly.
- `database/`: legacy/import database notes and SQL assets.
- `docs/`: design notes and future roadmap.

Data flow:

```text
AlecaFrame user data
  lastData.dat + cached data
        -> read-only Aleca adapter
        -> TradeFrame SQLite cache
        -> FastAPI service layer
        -> React UI
```

## Manual Development

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`.

## Version 1.0 Features

- WF chat-ready copy chunks for quickly sharing buy or sell part lists. TradeFrame splits long lists into chat-safe messages so you can move from analysis to actual Warframe trading without manually formatting every part.
- Dashboard with collection status, trading position, and portfolio history.
- Prime inventory, missing, tradable, published, strategic assets, and trade history views.
- Published List controls for explicitly choosing which tradable parts may be shared later.
- Settings for pricing display, value calculations, copy-message limits, and AlecaFrame data location.
- Read-only AlecaFrame adapter boundary.

## Roadmap

- P2P Published List exchange.
- Optional clan catalogue.
- Packaged desktop executable.

These modules can attach at the service layer without changing the Aleca adapter or UI contracts.
