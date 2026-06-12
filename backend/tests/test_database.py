from sqlalchemy import inspect, text

from database import build_engine, init_db


def test_init_db_creates_tables(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    tables = inspect(engine).get_table_names()
    assert "items" in tables
    assert "accounts" in tables


def test_sqlite_pragmas_applied(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path}/test.db")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
