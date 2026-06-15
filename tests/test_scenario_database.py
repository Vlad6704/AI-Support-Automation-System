import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import AgentRun, Customer, Invoice, TicketEvent
from app.repositories import DatabaseAgentRepository
from app.scenario_database import (
    concurrent_scenario_session_factory,
    create_scenario_database,
    ensure_scenario_database_schema,
    scenario_session_factory,
)
from app.scenario_world import load_world


PROJECT_DIR = Path(__file__).resolve().parents[1]
WORLD_PATH = PROJECT_DIR / "scenarios" / "world_1.json"
LARGE_WORLD_PATH = PROJECT_DIR / "scenarios" / "world_2.json"


class ScenarioDatabaseTests(unittest.TestCase):
    def test_ensures_new_tables_without_resetting_existing_scenario_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "existing.db"
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            try:
                Customer.__table__.create(engine)
                with Session(engine) as session:
                    session.add(
                        Customer(
                            id=1,
                            company_name="Preserved customer",
                            contact_email="preserved@example.test",
                            status="active",
                        )
                    )
                    session.commit()
            finally:
                engine.dispose()

            ensure_scenario_database_schema(database_path)

            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            try:
                with Session(engine) as session:
                    customer = session.get(Customer, 1)
                    self.assertIsNotNone(customer)
                    self.assertEqual(customer.company_name, "Preserved customer")
                    self.assertEqual(list(session.scalars(select(AgentRun)).all()), [])
                    self.assertEqual(list(session.scalars(select(TicketEvent)).all()), [])
            finally:
                engine.dispose()

    def test_rejects_existing_table_with_outdated_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "outdated.db"
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            try:
                Base.metadata.create_all(engine)
                with engine.begin() as connection:
                    connection.exec_driver_sql("DROP TABLE agent_runs")
                    connection.exec_driver_sql(
                        "CREATE TABLE agent_runs (id INTEGER PRIMARY KEY)"
                    )
            finally:
                engine.dispose()

            with self.assertRaisesRegex(RuntimeError, "schema is outdated"):
                ensure_scenario_database_schema(database_path)

    def test_creates_database_from_world_and_real_repository_reads_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "world_1.db"
            database_url = create_scenario_database(WORLD_PATH, database_path)
            engine = create_engine(database_url)
            try:
                with Session(engine) as session:
                    customer_count = session.scalar(
                        select(func.count()).select_from(Customer)
                    )
                self.assertGreater(customer_count or 0, 0)

                customer = DatabaseAgentRepository(
                    sessionmaker(bind=engine)
                ).get_customer_by_id(1)

                self.assertIsNotNone(customer)
                expected_customer = load_world(WORLD_PATH).customers[0]
                self.assertEqual(customer["company_name"], expected_customer.company_name)
            finally:
                engine.dispose()

    def test_reset_replaces_changes_with_original_world(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "world_1.db"
            database_url = create_scenario_database(WORLD_PATH, database_path)
            engine = create_engine(database_url)
            with Session(engine) as session:
                session.add(
                    Invoice(
                        invoice_id=9999,
                        start_date="2026-01-01",
                        end_date="2026-01-31",
                        amount="1.00",
                        refundable=False,
                    )
                )
                session.commit()
            engine.dispose()

            create_scenario_database(WORLD_PATH, database_path)
            engine = create_engine(database_url)
            try:
                with Session(engine) as session:
                    self.assertIsNone(session.get(Invoice, 9999))
            finally:
                engine.dispose()

    def test_in_memory_scenario_factories_are_isolated(self) -> None:
        with scenario_session_factory(WORLD_PATH) as first_sessions:
            with first_sessions() as session:
                session.add(
                    Invoice(
                        invoice_id=9999,
                        start_date="2026-01-01",
                        end_date="2026-01-31",
                        amount="1.00",
                        refundable=False,
                    )
                )
                session.commit()

            with scenario_session_factory(WORLD_PATH) as second_sessions:
                with second_sessions() as session:
                    self.assertIsNone(session.get(Invoice, 9999))

    def test_concurrent_scenario_factory_supports_parallel_queries(self) -> None:
        with concurrent_scenario_session_factory(LARGE_WORLD_PATH) as sessions:
            repository = DatabaseAgentRepository(sessions)

            def query_delivery_logs() -> int:
                result = repository.get_webhook_delivery_logs(
                    2,
                    where={
                        "match": "all",
                        "conditions": [
                            {
                                "column": "created_at",
                                "operator": "gte",
                                "value": "2026-06-01T00:00:00Z",
                            },
                            {
                                "column": "created_at",
                                "operator": "lt",
                                "value": "2026-07-01T00:00:00Z",
                            },
                            {
                                "column": "delivery_status",
                                "operator": "eq",
                                "value": "delivered",
                            },
                        ],
                    },
                    limit=1,
                )
                return result["count"]

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(lambda _: query_delivery_logs(), range(20)))

        self.assertEqual(len(results), 20)
        self.assertTrue(all(result > 0 for result in results))
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main()
