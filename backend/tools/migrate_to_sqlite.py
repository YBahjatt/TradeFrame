from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, delete, func, insert, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import Base, engine as source_engine
from app.models import entities  # noqa: F401 - imports mapped tables into Base metadata


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def migrate(output: Path) -> dict[str, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    target_engine = create_engine(sqlite_url(output), future=True)
    Base.metadata.create_all(target_engine)

    copied: dict[str, int] = {}
    with source_engine.connect() as source, target_engine.begin() as target:
        for table in Base.metadata.sorted_tables:
            rows = [dict(row._mapping) for row in source.execute(select(table))]
            target.execute(delete(table))
            if rows:
                target.execute(insert(table), rows)
            copied[table.name] = len(rows)
    return copied


def verify(path: Path) -> dict[str, int]:
    target_engine = create_engine(sqlite_url(path), future=True)
    counts: dict[str, int] = {}
    with target_engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            counts[table.name] = int(connection.execute(select(func.count()).select_from(table)).scalar_one())
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the current TradeFrame database into a local SQLite file.")
    parser.add_argument("--output", default="../data/tradeframe.sqlite3", help="SQLite output path, relative to backend/.")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = Path.cwd() / output
    output = output.resolve()

    copied = migrate(output)
    verified = verify(output)
    print(f"SQLite database: {output}")
    print("Copied rows:")
    for table_name in sorted(copied):
        print(f"  {table_name}: {copied[table_name]} copied, {verified.get(table_name, 0)} verified")


if __name__ == "__main__":
    main()
