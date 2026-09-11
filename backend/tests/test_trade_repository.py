from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.entities import Trade
from app.repositories.base import TradeRepository


def test_upsert_restores_resubmitted_deleted_trade() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repository = TradeRepository(session)

    repository.upsert(
        Trade(
            source="BackGround.html.log",
            source_line=1024,
            traded_at=datetime(2026, 9, 10, 16, 12, 48),
            partner="lXenoll",
            given_text="Nami Skyla Prime Blueprint",
            received_text="Nova Prime Blueprint",
            duplicate_decision="deleted",
        )
    )
    session.commit()

    existing = session.query(Trade).one()
    existing.duplicate_decision = "deleted"
    existing.analysis_given_value = 8
    existing.analysis_received_value = 20
    existing.analysis_given_items = '[{"name":"Old Given"}]'
    existing.analysis_received_items = '[{"name":"Old Received"}]'
    existing.analysis_priced_at = datetime(2026, 8, 14, 13, 0, 47)
    existing.analysis_price_mode = "snapshot"
    session.commit()

    repository.upsert(
        Trade(
            source="BackGround.html.log",
            source_line=1024,
            traded_at=datetime(2026, 9, 10, 16, 12, 48),
            partner="lXenoll",
            given_text="Nami Skyla Prime Blueprint",
            received_text="Nova Prime Blueprint",
        )
    )
    session.commit()

    restored = session.query(Trade).one()
    assert restored.duplicate_decision is None
    assert restored.analysis_given_items is None
    assert restored.analysis_received_items is None
    assert restored.analysis_priced_at is None
    assert repository.analysis_rows() == [restored]


def test_upsert_clears_analysis_cache_when_trade_text_changes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repository = TradeRepository(session)

    repository.upsert(
        Trade(
            source="BackGround.html.log",
            source_line=1024,
            traded_at=datetime(2026, 9, 10, 16, 12, 48),
            partner="lXenoll",
            given_text="Styanax Prime Neuroptics Blueprint",
            received_text="Gara Prime Chassis Blueprint\nRevenant Prime Chassis Blueprint",
        )
    )
    session.commit()

    existing = session.query(Trade).one()
    existing.analysis_given_items = '[{"name":"Styanax Prime Neuroptics Blueprint"}]'
    existing.analysis_received_items = '[{"name":"Gara Prime Chassis Blueprint"}]'
    existing.analysis_priced_at = datetime(2026, 8, 14, 13, 0, 47)
    session.commit()

    repository.upsert(
        Trade(
            source="BackGround.html.log",
            source_line=1024,
            traded_at=datetime(2026, 9, 10, 16, 12, 48),
            partner="lXenoll",
            given_text="Nami Skyla Prime Blueprint",
            received_text="Nova Prime Blueprint",
        )
    )
    session.commit()

    restored = session.query(Trade).one()
    assert restored.given_text == "Nami Skyla Prime Blueprint"
    assert restored.received_text == "Nova Prime Blueprint"
    assert restored.analysis_given_items is None
    assert restored.analysis_received_items is None
