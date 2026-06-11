import unittest
from pathlib import Path

from app.repositories import DatabaseAgentRepository
from app.scenario_database import scenario_session_factory


WORLD_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "world_1.json"
LARGE_WORLD_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "world_2.json"


class AgentRepositoryWebhookQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sessions_context = scenario_session_factory(WORLD_PATH)
        self.sessions = self.sessions_context.__enter__()
        self.repository = DatabaseAgentRepository(self.sessions)

    def tearDown(self) -> None:
        self.sessions_context.__exit__(None, None, None)

    def test_delivery_query_filters_and_counts_within_customer(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [
                    {"column": "delivery_status", "operator": "eq", "value": "delivered"},
                    {"column": "status_code", "operator": "eq", "value": 200},
                ],
            },
            limit=2,
        )

        self.assertEqual(result["count"], 4)
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(all(row["customer_id"] == 2 for row in result["rows"]))
        self.assertTrue(all(row["status_code"] == 200 for row in result["rows"]))

    def test_endpoint_query_filters_and_counts_within_customer(self) -> None:
        result = self.repository.get_webhook_endpoints(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "status", "operator": "eq", "value": "active"}],
            },
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["id"], 2)

    def test_customer_id_cannot_be_overridden_by_filter(self) -> None:
        with self.assertRaisesRegex(ValueError, "customer_id is fixed"):
            self.repository.get_webhook_delivery_logs(
                2,
                where={
                    "match": "all",
                    "conditions": [{"column": "customer_id", "operator": "eq", "value": 1}],
                },
            )

    def test_unknown_filter_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid WebhookEndpoint where column"):
            self.repository.get_webhook_endpoints(
                2,
                where={
                    "match": "all",
                    "conditions": [{"column": "unknown", "operator": "eq", "value": "value"}],
                },
            )

    def test_datetime_filter_accepts_iso_string(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "created_at", "operator": "eq", "value": "2026-06-08T16:20:00.000000"}],
            },
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["id"], 7)

    def test_last_attempt_at_filter_accepts_iso_string(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "last_attempt_at", "operator": "eq", "value": "2026-05-09T10:08:00"}],
            },
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["id"], 8)

    def test_endpoint_created_at_filter_accepts_iso_string(self) -> None:
        result = self.repository.get_webhook_endpoints(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "created_at", "operator": "eq", "value": "2026-05-01T10:00:00.000000"}],
            },
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["id"], 2)

    def test_datetime_filter_can_be_combined_with_other_filters(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [
                    {"column": "created_at", "operator": "eq", "value": "2026-05-09T10:00:00"},
                    {"column": "delivery_status", "operator": "eq", "value": "failed"},
                    {"column": "status_code", "operator": "eq", "value": 500},
                ],
            },
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["id"], 8)

    def test_valid_datetime_filter_with_no_match_returns_empty_result(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "created_at", "operator": "eq", "value": "2020-01-01T00:00:00"}],
            },
        )

        self.assertEqual(result, {"rows": [], "count": 0})

    def test_non_datetime_string_filter_remains_unchanged(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "event_type", "operator": "eq", "value": "payment.failed"}],
            },
        )

        self.assertEqual(result["count"], 3)

    def test_invalid_datetime_filter_is_rejected_cleanly(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Invalid WebhookDeliveryLog filter value for created_at",
        ):
            self.repository.get_webhook_delivery_logs(
                2,
                where={
                    "match": "all",
                    "conditions": [{"column": "created_at", "operator": "eq", "value": "not-a-timestamp"}],
                },
            )

    def test_invalid_last_attempt_at_filter_is_rejected_cleanly(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Invalid WebhookDeliveryLog filter value for last_attempt_at",
        ):
            self.repository.get_webhook_delivery_logs(
                2,
                where={
                    "match": "all",
                    "conditions": [{"column": "last_attempt_at", "operator": "eq", "value": "yesterday"}],
                },
            )

    def test_datetime_filter_rejects_object_before_sql_execution(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected ISO timestamp string, got dict",
        ):
            self.repository.get_webhook_delivery_logs(
                2,
                where={
                    "match": "all",
                    "conditions": [{"column": "created_at", "operator": "eq", "value": {}}],
                },
            )

    def test_datetime_filter_accepts_python_datetime(self) -> None:
        from datetime import datetime

        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [{"column": "created_at", "operator": "eq", "value": datetime.fromisoformat("2026-06-08T16:20:00")}],
            },
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["id"], 7)

    def test_datetime_range_query(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [
                    {"column": "created_at", "operator": "gte", "value": "2026-06-01T00:00:00"},
                    {"column": "created_at", "operator": "lte", "value": "2026-06-30T23:59:59"},
                ],
            },
        )

        self.assertEqual(result["count"], 3)

    def test_any_query_uses_or_semantics(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "any",
                "conditions": [
                    {"column": "status_code", "operator": "eq", "value": 500},
                    {"column": "event_type", "operator": "eq", "value": "order.created"},
                ],
            },
        )

        self.assertEqual(result["count"], 3)

    def test_in_and_contains_operators(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [
                    {"column": "status_code", "operator": "in", "value": [200, 500]},
                    {"column": "event_type", "operator": "contains", "value": "payment"},
                ],
            },
        )

        self.assertEqual(result["count"], 3)

    def test_is_null_operator(self) -> None:
        result = self.repository.get_webhook_delivery_logs(
            2,
            where={
                "match": "all",
                "conditions": [
                    {"column": "error_message", "operator": "is_null", "value": None}
                ],
            },
        )

        self.assertEqual(result["count"], 4)

    def test_string_operator_rejects_non_string_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "starts_with requires a string column"):
            self.repository.get_webhook_delivery_logs(
                2,
                where={
                    "match": "all",
                    "conditions": [
                        {"column": "status_code", "operator": "starts_with", "value": "5"}
                    ],
                },
            )

    def test_in_operator_requires_non_empty_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "in requires a non-empty list"):
            self.repository.get_webhook_delivery_logs(
                2,
                where={
                    "match": "all",
                    "conditions": [
                        {"column": "status_code", "operator": "in", "value": []}
                    ],
                },
            )

    def test_customer_context_contains_only_last_30_webhook_items(self) -> None:
        with scenario_session_factory(LARGE_WORLD_PATH) as sessions:
            context = DatabaseAgentRepository(sessions).get_customer_context(2)

        delivery_logs = context["last_30_webhook_delivery_logs"]
        self.assertEqual(len(delivery_logs), 30)
        self.assertEqual(
            [row["id"] for row in delivery_logs],
            sorted((row["id"] for row in delivery_logs), reverse=True),
        )
        self.assertLessEqual(len(context["last_30_webhook_endpoints"]), 30)


if __name__ == "__main__":
    unittest.main()
