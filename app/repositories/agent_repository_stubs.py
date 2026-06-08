from datetime import datetime
from pathlib import Path
from collections.abc import Sequence
from typing import cast

from app.enums import AffectedService
from app.repositories.agent_repository_protocols import (
    CustomerData,
    CustomerContextData,
    InvoiceData,
    SerializedRow,
    TicketHistoryData,
)
from app.repositories.world_schema import (
    WorldData,
    WorldRow,
    load_world,
)

STUBS_DIR = Path(__file__).resolve().parents[2] / "stubs"

def _load_world(world: str) -> WorldData:
    world_path = STUBS_DIR / f"{world}.json"
    return load_world(world_path)


def _serialize_row(row: WorldRow) -> SerializedRow:
    return cast(SerializedRow, row.model_dump(mode="json"))


class StubAgentRepository:
    def __init__(self, world: str = "world_1") -> None:
        self.world = _load_world(world)

    def get_customer_by_id(self, customer_id: int) -> CustomerData | None:
        customer = next(
            (row for row in self.world.customers if row.id == customer_id),
            None,
        )
        return cast(CustomerData, customer.model_dump()) if customer else None

    def get_ticket_by_id(self, ticket_id: int) -> TicketHistoryData | None:
        ticket = next(
            (row for row in self.world.ticket_history if row.id == ticket_id),
            None,
        )
        return cast(TicketHistoryData, ticket.model_dump()) if ticket else None

    def get_first_ticket(self) -> TicketHistoryData | None:
        tickets = sorted(self.world.ticket_history, key=lambda row: row.id)
        return cast(TicketHistoryData, tickets[0].model_dump()) if tickets else None

    def get_invoice_by_id(self, invoice_id: int) -> InvoiceData | None:
        invoice = next(
            (
                row for row in self.world.invoices if row.invoice_id == invoice_id
            ),
            None,
        )
        return cast(InvoiceData, invoice.model_dump()) if invoice else None

    def get_customer_context(self, customer_id: int) -> CustomerContextData:
        customer = next(
            (row for row in self.world.customers if row.id == customer_id),
            None,
        )
        return {
            "customer": _serialize_row(customer) if customer else None,
            "subscriptions": self._latest_for_customer(
                self.world.subscriptions, customer_id
            ),
            "api_usage_logs": self._latest_for_customer(
                self.world.api_usage_logs, customer_id
            ),
            "ticket_history": self._latest_for_customer(
                self.world.ticket_history, customer_id
            ),
            "webhook_delivery_logs": self._latest_for_customer(
                self.world.webhook_delivery_logs, customer_id
            ),
        }

    def get_incidents(
        self,
        affected_service: AffectedService,
        limit: int = 20,
    ) -> list[SerializedRow]:
        safe_limit = max(1, min(limit, 20))
        rows = [
            row for row in self.world.incidents if row.affected_service == affected_service
        ]
        rows.sort(key=lambda row: row.started_at, reverse=True)
        return [_serialize_row(row) for row in rows[:safe_limit]]

    def get_deployments(
        self,
        deployed_from: datetime | None = None,
        deployed_to: datetime | None = None,
    ) -> list[SerializedRow]:
        rows = []
        for row in self.world.deployments:
            deployed_at = row.deployed_at
            if deployed_from is not None and deployed_at < deployed_from:
                continue
            if deployed_to is not None and deployed_at > deployed_to:
                continue
            rows.append(row)

        rows.sort(key=lambda row: row.deployed_at, reverse=True)
        return [_serialize_row(row) for row in rows[:10]]

    def _latest_for_customer(
        self,
        rows: Sequence[WorldRow],
        customer_id: int,
        limit: int = 50,
    ) -> list[SerializedRow]:
        customer_rows = [
            row for row in rows if getattr(row, "customer_id", None) == customer_id
        ]
        customer_rows.sort(key=lambda row: row.id, reverse=True)
        return [_serialize_row(row) for row in customer_rows[:limit]]
