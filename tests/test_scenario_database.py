import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Customer, Invoice
from app.repositories import DatabaseAgentRepository
from app.scenario_database import (
    concurrent_scenario_session_factory,
    create_scenario_database,
    scenario_session_factory,
)
from app.scenario_world import load_world


PROJECT_DIR = Path(__file__).resolve().parents[1]
WORLD_PATH = PROJECT_DIR / "scenarios" / "world_1.json"
LARGE_WORLD_PATH = PROJECT_DIR / "scenarios" / "world_2.json"


class ScenarioDatabaseTests(unittest.TestCase):
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
