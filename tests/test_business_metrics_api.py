import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.enums import (
    AgentRunHumanReviewResult,
    AgentRunOutcome,
    MessageSource,
    TicketStatus,
)
from app.main import app
from app.models import (
    AgentRun,
    Customer,
    Message,
    Subscription,
    TicketEvent,
    TicketHistory,
)


class BusinessMetricsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        start = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

        with Session(cls.engine) as db:
            db.add(
                Customer(
                    id=1,
                    company_name="Acme",
                    contact_email="support@acme.test",
                    status="active",
                )
            )
            db.add(
                Subscription(
                    id=1,
                    customer_id=1,
                    plan="pro",
                    monthly_event_limit=1000,
                    current_month_events=10,
                    rate_limit_per_minute=100,
                    sla_response_time_minutes=10,
                    support_tier="priority",
                    is_over_limit=False,
                )
            )
            for ticket_id in range(1, 4):
                db.add(
                    TicketHistory(
                        id=ticket_id,
                        customer_id=1,
                        title=f"Ticket {ticket_id}",
                        description="Please investigate.",
                        status=TicketStatus.OPEN,
                        created_at=start,
                        updated_at=start,
                    )
                )

            db.add_all(
                [
                    AgentRun(
                        id=1,
                        ticket_id=1,
                        agent_name="main-agent",
                        started_at=start,
                        completed_at=start + timedelta(seconds=1),
                        outcome=AgentRunOutcome.AUTOMATED,
                        human_review_required=False,
                        model_cost=Decimal("1.000000"),
                    ),
                    AgentRun(
                        id=2,
                        ticket_id=2,
                        agent_name="main-agent",
                        started_at=start,
                        completed_at=start + timedelta(seconds=2),
                        outcome=AgentRunOutcome.AWAITING_REVIEW,
                        human_review_required=True,
                        human_review_result=(
                            AgentRunHumanReviewResult.ACCEPTED_WITHOUT_EDITING
                        ),
                        edit_percentage=Decimal("0.0000"),
                        model_cost=Decimal("2.000000"),
                    ),
                    AgentRun(
                        id=3,
                        ticket_id=3,
                        agent_name="main-agent",
                        started_at=start,
                        completed_at=start + timedelta(seconds=3),
                        outcome=AgentRunOutcome.AUTOMATED,
                        human_review_required=False,
                    ),
                ]
            )
            db.add_all(
                [
                    TicketEvent(
                        ticket_id=1,
                        event_type="response_sent",
                        actor_type="agent",
                        created_at=start + timedelta(minutes=5),
                    ),
                    TicketEvent(
                        ticket_id=2,
                        event_type="response_sent",
                        actor_type="agent",
                        created_at=start + timedelta(minutes=15),
                    ),
                    TicketEvent(
                        ticket_id=3,
                        event_type="response_sent",
                        actor_type="agent",
                        created_at=start + timedelta(minutes=2),
                    ),
                ]
            )
            for ticket_id in range(1, 4):
                db.add(
                    Message(
                        customer_id=1,
                        ticket_id=ticket_id,
                        message="Initial request",
                        source=MessageSource.USER,
                        created_at=start,
                        updated_at=start,
                    )
                )
            db.add(
                Message(
                    customer_id=1,
                    ticket_id=3,
                    message="I still need help",
                    source=MessageSource.USER,
                    created_at=start + timedelta(minutes=3),
                    updated_at=start + timedelta(minutes=3),
                )
            )
            db.commit()

        def override_get_db():
            with Session(cls.engine) as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_returns_agent_business_metrics(self) -> None:
        response = self.client.get(
            "/api/metrics/agent-business",
            params={"manual_handling_baseline_minutes": 20},
        )

        self.assertEqual(response.status_code, 200)
        metrics = response.json()
        self.assertEqual(metrics["tickets_agent_involved"], 3)
        self.assertEqual(metrics["tickets_handled_automatically"], 2)
        self.assertEqual(metrics["tickets_handled_with_human_review"], 1)
        self.assertEqual(metrics["tickets_accepted_without_editing"], 1)
        self.assertEqual(metrics["potential_time_saved_minutes"], 40)
        self.assertEqual(metrics["total_model_cost"], 3)
        self.assertEqual(metrics["runs_with_recorded_cost"], 2)
        self.assertEqual(metrics["run_duration"]["p01_ms"], 1020)
        self.assertEqual(metrics["run_duration"]["median_ms"], 2000)
        self.assertEqual(metrics["sla_compliance"]["rate"], 0.6667)
        self.assertEqual(metrics["one_message_resolution"]["rate"], 0.6667)
        self.assertEqual(metrics["repeat_contact"]["rate"], 0.3333)


if __name__ == "__main__":
    unittest.main()
