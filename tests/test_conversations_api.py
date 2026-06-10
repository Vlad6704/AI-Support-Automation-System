import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.api.providers import get_ticket_conversation_service
from app.enums import MessageSource, TicketStatus
from app.main import app
from app.models import Customer, Message, TicketHistory
from app.repositories import DatabaseTicketConversationRepository


class ConversationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)

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
                TicketHistory(
                    id=1,
                    customer_id=1,
                    title="Webhook payload is incorrect",
                    description="Please investigate.",
                    status=TicketStatus.OPEN,
                )
            )
            db.add(
                Message(
                    id=1,
                    customer_id=1,
                    ticket_id=1,
                    message="The amount field is incorrect.",
                    source=MessageSource.USER,
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

    def test_lists_tickets_and_messages(self) -> None:
        tickets = self.client.get("/api/tickets")
        messages = self.client.get("/api/tickets/1/messages")

        self.assertEqual(tickets.status_code, 200)
        self.assertTrue(
            any(
                ticket["title"] == "Webhook payload is incorrect"
                for ticket in tickets.json()
            )
        )
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(messages.json()[0]["source"], "user")

    def test_service_provider_uses_request_database_session(self) -> None:
        with Session(self.engine) as db:
            service = get_ticket_conversation_service(db)

            self.assertIsInstance(
                service.repository,
                DatabaseTicketConversationRepository,
            )
            self.assertIs(service.repository.db, db)

    def test_creates_support_reply(self) -> None:
        agent_message = Message(
            id=10,
            customer_id=1,
            ticket_id=1,
            message="Please send the affected event ID.",
            source=MessageSource.SUPPORT_TEAM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        with patch(
            "app.services.ticket_agent.TicketAgentService.run_and_store_response",
            return_value=agent_message,
        ):
            response = self.client.post(
                "/api/tickets/1/messages",
                json={"message": "The expected amount is 120.50."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user_message"]["source"], "user")
        self.assertEqual(response.json()["agent_message"]["source"], "support_team")

    def test_creates_ticket_and_schedules_agent_response(self) -> None:
        with patch(
            "app.api.router.conversations.run_agent_and_store_ticket_response"
        ) as run_agent:
            response = self.client.post(
                "/api/tickets",
                json={
                    "customer_id": 1,
                    "title": "New webhook issue",
                    "description": "A webhook contains unexpected fields.",
                },
            )

        self.assertEqual(response.status_code, 201)
        ticket_id = response.json()["id"]
        run_agent.assert_called_once_with(ticket_id, new_thread=True)
        messages = self.client.get(f"/api/tickets/{ticket_id}/messages").json()
        self.assertEqual(messages[0]["source"], "user")

    def test_rejects_blank_ticket_fields_and_unknown_customer(self) -> None:
        blank = self.client.post(
            "/api/tickets",
            json={"customer_id": 1, "title": " ", "description": " "},
        )
        missing_customer = self.client.post(
            "/api/tickets",
            json={
                "customer_id": 999,
                "title": "Valid title",
                "description": "Valid description",
            },
        )

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(missing_customer.status_code, 422)

    def test_serves_inbox_page(self) -> None:
        response = self.client.get("/")
        new_ticket = self.client.get("/tickets/new")
        ticket = self.client.get("/tickets/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Support inbox", response.text)
        self.assertIn("Create a support ticket", new_ticket.text)
        self.assertIn("Waiting for the support agent", ticket.text)


if __name__ == "__main__":
    unittest.main()
