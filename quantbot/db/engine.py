"""Engine/session helpers for the SQLite traceability database.

SQLite quirks handled here:
- Foreign keys are OFF by default in SQLite; a connect-event turns the
  pragma on for every connection so FK violations fail loudly.
- Immutability of the pure-trace tables is enforced with BEFORE UPDATE /
  BEFORE DELETE triggers that RAISE(ABORT), created in ``init_db``.
"""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from quantbot.db.models import IMMUTABLE_TABLES, Base


def create_db_engine(db_path: Path) -> Engine:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables and the append-only triggers (idempotent)."""
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS "
                        f"immutable_{table}_{operation.lower()} "
                        f"BEFORE {operation} ON {table} "
                        f"BEGIN "
                        f"SELECT RAISE(ABORT, "
                        f"'{table} is append-only: {operation} forbidden'); "
                        f"END"
                    )
                )
