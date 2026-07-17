from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantbot.db import create_db_engine, create_session_factory, init_db


@pytest.fixture()
def db_engine(tmp_path: Path) -> Engine:
    engine = create_db_engine(tmp_path / "test.sqlite")
    init_db(engine)
    return engine


@pytest.fixture()
def db_session(db_engine: Engine) -> Session:
    factory = create_session_factory(db_engine)
    with factory() as session:
        yield session
