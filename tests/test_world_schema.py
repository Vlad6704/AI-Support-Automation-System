import unittest
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.repositories.agent_repository_stubs import StubAgentRepository
from app.repositories.world_schema import (
    WORLD_MODEL_SCHEMAS,
    load_world,
    validate_world_schema_matches_database_models,
)

STUBS_DIR = Path(__file__).resolve().parents[1] / "stubs"


class WorldSchemaTests(unittest.TestCase):
    def test_world_schema_matches_database_models(self) -> None:
        validate_world_schema_matches_database_models()

    def test_all_worlds_are_valid(self) -> None:
        world_paths = list(STUBS_DIR.glob("*.json"))
        self.assertTrue(world_paths, "No stub worlds found")
        for world_path in world_paths:
            with self.subTest(world=world_path.name):
                load_world(world_path)

    def test_current_database_rows_match_world_schemas(self) -> None:
        db = SessionLocal()
        try:
            for database_model, world_schema in WORLD_MODEL_SCHEMAS.items():
                with self.subTest(model=database_model.__name__):
                    for row in db.scalars(select(database_model)).all():
                        world_schema.model_validate(row)
        finally:
            db.close()

    def test_webhook_context_contains_endpoints_and_event_payloads(self) -> None:
        context = StubAgentRepository().get_customer_context(2)

        self.assertEqual(
            context["webhook_endpoints"][0]["events"],
            ["order.created", "payment.failed"],
        )
        self.assertEqual(
            context["api_usage_logs"][0]["payload"]["payment_id"],
            "pay_2002",
        )
        self.assertTrue(
            all(
                log["webhook_endpoint_id"] == 2
                for log in context["webhook_delivery_logs"]
            )
        )
        self.assertEqual(context["messages"][0]["source"], "support_team")
        self.assertEqual(context["messages"][0]["ticket_id"], 5)


if __name__ == "__main__":
    unittest.main()
