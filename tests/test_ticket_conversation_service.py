import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.enums import MessageSource
from app.models import Customer, Message, TicketHistory
from app.repositories import (
    DatabaseTicketConversationRepository,
    database_ticket_conversation_repository,
)
from app.services import (
    AgentResponseError,
    CustomerNotFoundError,
    TicketAgentService,
    TicketNotFoundError,
    TicketConversationService,
)


class TicketConversationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
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
                    title="Webhook issue",
                    description="Please investigate.",
                    status="open",
                )
            )
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def create_service(self, db: Session) -> TicketConversationService:
        return TicketConversationService(
            DatabaseTicketConversationRepository(db),
            TicketAgentService(database_ticket_conversation_repository),
        )

    def test_creates_ticket_with_initial_user_message(self) -> None:
        with Session(self.engine) as db:
            ticket = self.create_service(db).create_ticket(
                customer_id=1,
                title="New webhook issue",
                description="A webhook contains unexpected fields.",
            )
            ticket_id = ticket.id

        with Session(self.engine) as db:
            stored_ticket = db.get(TicketHistory, ticket_id)
            message = db.scalars(
                select(Message).where(Message.ticket_id == ticket_id)
            ).one()

        self.assertEqual(stored_ticket.title, "New webhook issue")
        self.assertEqual(message.message, "A webhook contains unexpected fields.")
        self.assertEqual(message.source, MessageSource.USER)

    def test_rejects_ticket_for_unknown_customer(self) -> None:
        with Session(self.engine) as db:
            with self.assertRaises(CustomerNotFoundError):
                self.create_service(db).create_ticket(
                    customer_id=999,
                    title="New webhook issue",
                    description="A webhook contains unexpected fields.",
                )

    def test_lists_customers_tickets_and_messages(self) -> None:
        with Session(self.engine) as db:
            service = self.create_service(db)
            customers = service.list_customers()
            tickets = service.list_tickets()
            messages = service.list_messages(1)

        self.assertEqual(customers[0].company_name, "Acme")
        self.assertEqual(tickets[0].title, "Webhook issue")
        self.assertEqual(messages, [])

    def test_rejects_reads_for_unknown_ticket(self) -> None:
        with Session(self.engine) as db:
            service = self.create_service(db)
            with self.assertRaises(TicketNotFoundError):
                service.get_ticket(999)
            with self.assertRaises(TicketNotFoundError):
                service.list_messages(999)

    def test_creates_user_message_and_returns_agent_response(self) -> None:
        agent_message = Message(
            id=10,
            customer_id=1,
            ticket_id=1,
            message="Please provide the event ID.",
            source=MessageSource.SUPPORT_TEAM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        with (
            Session(self.engine) as db,
            patch.object(
                TicketAgentService,
                "run_and_store_response",
                return_value=agent_message,
            ) as run_agent,
        ):
            conversation = self.create_service(db).create_user_message(
                1,
                message="The amount is incorrect.",
            )

        self.assertEqual(conversation.user_message.source, MessageSource.USER)
        self.assertEqual(conversation.agent_message, agent_message)
        run_agent.assert_called_once_with(1)

    def test_reports_agent_response_failure(self) -> None:
        with (
            Session(self.engine) as db,
            patch.object(
                TicketAgentService,
                "run_and_store_response",
                side_effect=ValueError("Agent failed"),
            ),
        ):
            with self.assertRaises(AgentResponseError):
                self.create_service(db).create_user_message(
                    1,
                    message="The amount is incorrect.",
                )

    @patch("app.services.ticket_agent.delete_ticket_thread")
    @patch("app.services.ticket_agent.invoke_main_agent_for_ticket")
    def test_stores_agent_draft_as_support_message(
        self,
        invoke_agent,
        delete_thread,
    ) -> None:
        invoke_agent.return_value = {"draft_response": "Please provide the event ID."}

        with patch(
            "app.repositories.ticket_conversation_repository.SessionLocal",
            side_effect=lambda: Session(self.engine),
        ):
            message = TicketAgentService(
                database_ticket_conversation_repository
            ).run_and_store_response(1, new_thread=True)

        self.assertEqual(message.source, MessageSource.SUPPORT_TEAM)
        delete_thread.assert_called_once_with(1)
        with Session(self.engine) as db:
            stored = db.scalars(select(Message)).one()
            self.assertEqual(stored.message, "Please provide the event ID.")


if __name__ == "__main__":
    unittest.main()
