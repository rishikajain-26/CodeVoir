from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = _DB_DIR / "opportunities.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from .models import CrawlLog, Opportunity  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()


def _migrate_add_columns() -> None:
    """Add new columns to existing DB without dropping data (SQLite-safe)."""
    migrations = [
        "ALTER TABLE opportunities ADD COLUMN is_platform_company INTEGER DEFAULT 0",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                pass  # Column already exists — skip
