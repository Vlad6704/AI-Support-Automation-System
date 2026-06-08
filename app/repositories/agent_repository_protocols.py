from datetime import datetime
from typing import Any, Protocol, TypedDict

from app.enums import AffectedService


class CustomerData(TypedDict):
    id: int
    company_name: str
    contact_email: str
    region: str | None
    plan: str | None
    status: str
    created_at: datetime


class TicketHistoryData(TypedDict):
    id: int
    customer_id: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: str
    category: str | None
    updated_by: str | None
    resolution_summery: str | None


class InvoiceData(TypedDict):
    invoice_id: int
    start_date: str
    end_date: str
    amount: str
    refundable: bool


class AgentRepository(Protocol):
    def get_customer_by_id(self, customer_id: int) -> CustomerData | None: ...

    def get_ticket_by_id(self, ticket_id: int) -> TicketHistoryData | None: ...

    def get_first_ticket(self) -> TicketHistoryData | None: ...

    def get_invoice_by_id(self, invoice_id: int) -> InvoiceData | None: ...

    def get_customer_context(self, customer_id: int) -> dict[str, Any]: ...

    def get_incidents(
        self,
        affected_service: AffectedService,
        limit: int = 20,
    ) -> list[dict[str, Any]]: ...

    def get_deployments(
        self,
        deployed_from: datetime | None = None,
        deployed_to: datetime | None = None,
    ) -> list[dict[str, Any]]: ...
