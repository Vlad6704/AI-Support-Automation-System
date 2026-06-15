from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import tempfile

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.scenario_world import (
    WORLD_TABLES,
    WorldData,
    load_world,
    validate_world_schema_matches_database_models,
)


def sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.resolve().as_posix()}"


def seed_world(engine: Engine, world: WorldData, *, reset: bool = True) -> None:
    validate_world_schema_matches_database_models()
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for model, _, rows_name in WORLD_TABLES:
            rows = getattr(world, rows_name)
            session.add_all(model(**row.model_dump()) for row in rows)
        session.commit()


def create_scenario_database(
    world_path: Path,
    database_path: Path,
    *,
    reset: bool = True,
) -> str:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = sqlite_url(database_path)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    try:
        seed_world(engine, load_world(world_path), reset=reset)
    finally:
        engine.dispose()
    return database_url


def ensure_scenario_database_schema(database_path: Path) -> str:
    """Create newly added tables without resetting existing scenario data."""
    database_url = sqlite_url(database_path)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    try:
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        mismatches: list[str] = []
        for table in Base.metadata.sorted_tables:
            actual_columns = {
                str(column["name"])
                for column in inspector.get_columns(table.name)
            }
            expected_columns = set(table.columns.keys())
            if actual_columns != expected_columns:
                mismatches.append(
                    f"{table.name}: expected={sorted(expected_columns)}, "
                    f"actual={sorted(actual_columns)}"
                )
        if mismatches:
            raise RuntimeError(
                "Existing scenario database schema is outdated. "
                "Reset it with the scenario-seed-and-run command. Differences: "
                + "; ".join(mismatches)
            )
    finally:
        engine.dispose()
    return database_url


@contextmanager
def scenario_session_factory(
    world_path: Path,
) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        seed_world(engine, load_world(world_path))
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    finally:
        engine.dispose()


@contextmanager
def concurrent_scenario_session_factory(
    world_path: Path,
) -> Iterator[sessionmaker[Session]]:
    """Create an isolated file-backed scenario database for concurrent queries."""
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / f"{world_path.stem}.db"
        database_url = create_scenario_database(world_path, database_path)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        try:
            yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
        finally:
            engine.dispose()
