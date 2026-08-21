from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.adapters.aleca import AlecaAdapter, AlecaAdapterError
from app.config import get_settings
from app.database.bootstrap import create_schema, seed_defaults
from app.database.session import SessionLocal
from app.services.portfolio import PortfolioService
from app.services.sync import SyncService


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup() -> None:
    create_schema()
    with SessionLocal() as db:
        seed_defaults(db)
        try:
            adapter = AlecaAdapter(settings.aleca_data_dir)
            SyncService(db, adapter).sync()
            PortfolioService(db).snapshot_today()
        except (AlecaAdapterError, FileNotFoundError, OSError, RuntimeError):
            pass
