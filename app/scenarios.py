import argparse
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCENARIO_SEEDS_DIR = PROJECT_DIR / "scenarios"
SCENARIO_DATABASES_DIR = PROJECT_DIR / ".scenarios"


def world_path(value: str) -> Path:
    path = Path(value)
    if path.suffix != ".json":
        path = SCENARIO_SEEDS_DIR / f"{value}.json"
    elif not path.is_absolute():
        path = PROJECT_DIR / path
    if not path.is_file():
        raise FileNotFoundError(f"Scenario world does not exist: {path}")
    return path


def database_path(world: Path, value: str | None) -> Path:
    if value is None:
        return SCENARIO_DATABASES_DIR / f"{world.stem}.db"
    path = Path(value)
    return path if path.is_absolute() else PROJECT_DIR / path


def prepare_scenario(world_value: str, database_value: str | None = None) -> str:
    world = world_path(world_value)
    database = database_path(world, database_value)

    from app.scenario_database import create_scenario_database

    return create_scenario_database(world, database)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and run databases seeded from scenario JSON worlds."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Reset and seed a scenario database.")
    seed_parser.add_argument("world", help="World name from scenarios/ or a JSON path.")
    seed_parser.add_argument("--database", help="Output database path.")

    run_parser = subparsers.add_parser(
        "run",
        help="Reset, seed, and run the application with a scenario database.",
    )
    run_parser.add_argument("world", help="World name from scenarios/ or a JSON path.")
    run_parser.add_argument("--database", help="Output database path.")
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", default=8000, type=int)

    start_parser = subparsers.add_parser(
        "start",
        help="Run the application with an existing scenario database.",
    )
    start_parser.add_argument("world", help="World name from scenarios/ or a JSON path.")
    start_parser.add_argument("--database", help="Existing scenario database path.")
    start_parser.add_argument("--host", default="127.0.0.1")
    start_parser.add_argument("--port", default=8000, type=int)

    args = parser.parse_args()
    world = world_path(args.world)
    target_database = database_path(world, args.database)
    if args.command == "start" and not target_database.is_file():
        raise FileNotFoundError(
            f"Scenario database does not exist: {target_database}. "
            f"Seed it first with: python -m app.scenarios seed {args.world}"
        )

    checkpoint_database = target_database.with_suffix(".checkpoints.db")
    os.environ["DATABASE_URL"] = (
        f"sqlite:///{target_database.resolve().as_posix()}"
    )
    os.environ["CHECKPOINT_DATABASE_PATH"] = str(checkpoint_database.resolve())

    if args.command == "seed":
        database_url = prepare_scenario(args.world, args.database)
        checkpoint_database.unlink(missing_ok=True)
        print(database_url)
        return

    if args.command == "run":
        prepare_scenario(args.world, args.database)
        checkpoint_database.unlink(missing_ok=True)

    import uvicorn

    uvicorn.run("main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
