from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

from app.enums import AffectedService
from app.repositories.agent_repository_protocols import (
    CustomerData,
    InvoiceData,
    TicketHistoryData,
)
from app.repositories.world_schema import load_world

STUBS_DIR = Path(__file__).resolve().parents[2] / "stubs"

def _load_world(world: str) -> dict[str, list[dict[str, Any]]]:
    world_path = STUBS_DIR / f"{world}.json"
    return cast(dict[str, list[dict[str, Any]]], load_world(world_path).model_dump())


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (
            value.isoformat()
            if isinstance(value, datetime)
            else value.value
            if isinstance(value, Enum)
            else value
        )
        for key, value in row.items()
    }


class StubAgentRepository:
    def __init__(self, world: str = "world_1") -> None:
        self.world = _load_world(world)

    def get_customer_by_id(self, customer_id: int) -> CustomerData | None:
        customer = next(
            (
                row
                for row in self.world.get("customers", [])
                if row["id"] == customer_id
            ),
            None,
        )
        return cast(CustomerData, deepcopy(customer)) if customer else None

    def get_ticket_by_id(self, ticket_id: int) -> TicketHistoryData | None:
        ticket = next(
            (
                row
                for row in self.world.get("ticket_history", [])
                if row["id"] == ticket_id
            ),
            None,
        )
        return cast(TicketHistoryData, deepcopy(ticket)) if ticket else None

    def get_first_ticket(self) -> TicketHistoryData | None:
        tickets = sorted(self.world.get("ticket_history", []), key=lambda row: row["id"])
        return cast(TicketHistoryData, deepcopy(tickets[0])) if tickets else None

    def get_invoice_by_id(self, invoice_id: int) -> InvoiceData | None:
        invoice = next(
            (
                row
                for row in self.world.get("invoices", [])
                if row["invoice_id"] == invoice_id
            ),
            None,
        )
        return cast(InvoiceData, deepcopy(invoice)) if invoice else None

    def get_customer_context(self, customer_id: int) -> dict[str, Any]:
        customer = self.get_customer_by_id(customer_id)
        return {
            "customer": _serialize_row(customer) if customer else None,
            "subscriptions": self._latest_for_customer("subscriptions", customer_id),
            "api_usage_logs": self._latest_for_customer("api_usage_logs", customer_id),
            "ticket_history": self._latest_for_customer("ticket_history", customer_id),
            "webhook_delivery_logs": self._latest_for_customer(
                "webhook_delivery_logs",
                customer_id,
            ),
        }

    def get_incidents(
        self,
        affected_service: AffectedService,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 20))
        rows = [
            row
            for row in self.world.get("incidents", [])
            if row.get("affected_service") == affected_service
        ]
        rows.sort(key=lambda row: row["started_at"], reverse=True)
        return [_serialize_row(deepcopy(row)) for row in rows[:safe_limit]]

    def get_deployments(
        self,
        deployed_from: datetime | None = None,
        deployed_to: datetime | None = None,
    ) -> list[dict[str, Any]]:
        rows = []
        for row in self.world.get("deployments", []):
            deployed_at = row.get("deployed_at")
            if not isinstance(deployed_at, datetime):
                continue
            if deployed_from is not None and deployed_at < deployed_from:
                continue
            if deployed_to is not None and deployed_at > deployed_to:
                continue
            rows.append(row)

        rows.sort(key=lambda row: row["deployed_at"], reverse=True)
        return [_serialize_row(deepcopy(row)) for row in rows[:10]]

    def _latest_for_customer(
        self,
        table: str,
        customer_id: int,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = [
            row
            for row in self.world.get(table, [])
            if row.get("customer_id") == customer_id
        ]
        rows.sort(key=lambda row: row["id"], reverse=True)
        return [_serialize_row(deepcopy(row)) for row in rows[:limit]]
