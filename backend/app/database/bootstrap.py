from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database.session import Base, engine
from app.models.entities import ScoringWeight


DEFAULT_WEIGHTS = {
    "complete_item": 100,
    "missing_2_to_1": 60,
    "missing_3_to_2": 40,
    "missing_4_to_3": 20,
    "new_unique_vaulted_part": 40,
    "new_unique_unvaulted_part": 20,
    "gain_duplicate": 0,
    "lose_duplicate": 0,
    "lose_last_copy": -1000,
}


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def migrate_schema() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "trades" not in table_names:
        return
    columns = {column["name"] for column in inspector.get_columns("trades")}
    migrations = {
        "analysis_given_value": "ALTER TABLE trades ADD COLUMN analysis_given_value FLOAT NULL",
        "analysis_received_value": "ALTER TABLE trades ADD COLUMN analysis_received_value FLOAT NULL",
        "analysis_given_items": "ALTER TABLE trades ADD COLUMN analysis_given_items TEXT NULL",
        "analysis_received_items": "ALTER TABLE trades ADD COLUMN analysis_received_items TEXT NULL",
        "analysis_priced_at": "ALTER TABLE trades ADD COLUMN analysis_priced_at DATETIME NULL",
        "analysis_price_mode": "ALTER TABLE trades ADD COLUMN analysis_price_mode VARCHAR(32) NULL",
        "duplicate_decision": "ALTER TABLE trades ADD COLUMN duplicate_decision VARCHAR(32) NULL",
    }
    with engine.begin() as connection:
        for column, sql in migrations.items():
            if column not in columns:
                connection.execute(text(sql))
    if "portfolio_snapshots" in table_names:
        snapshot_columns = {column["name"] for column in inspector.get_columns("portfolio_snapshots")}
        with engine.begin() as connection:
            if "unused_prime_parts" not in snapshot_columns:
                connection.execute(text("ALTER TABLE portfolio_snapshots ADD COLUMN unused_prime_parts INT NOT NULL DEFAULT 0"))
            if "unused_vaulted_parts" not in snapshot_columns:
                connection.execute(text("ALTER TABLE portfolio_snapshots ADD COLUMN unused_vaulted_parts INT NOT NULL DEFAULT 0"))
            if "platinum_balance" not in snapshot_columns:
                connection.execute(text("ALTER TABLE portfolio_snapshots ADD COLUMN platinum_balance INT NOT NULL DEFAULT 0"))


def seed_defaults(db: Session) -> None:
    for key, value in DEFAULT_WEIGHTS.items():
        if db.get(ScoringWeight, key) is None:
            db.add(ScoringWeight(key=key, value=value))
    db.commit()
