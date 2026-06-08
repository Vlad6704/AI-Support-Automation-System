from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from app.enums import AffectedService
from app.repositories import (
    select_customer_context_by_id,
    select_deployments_by_time_window,
    select_incidents_for_affected_service,
)


@tool
def select_customer_context(customer_id: int) -> dict[str, Any]:
    """Select customer-owned data from all customer tables except support_team_members."""
    return select_customer_context_by_id(customer_id)


@tool
def select_incidents_by_affected_service(
    affected_service: AffectedService,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Select incidents for an affected service, capped at 20 rows."""
    return select_incidents_for_affected_service(affected_service, limit)


@tool
def select_deployments(
    deployed_from: datetime | None = None,
    deployed_to: datetime | None = None,
) -> list[dict[str, Any]]:
    """Select deployments by optional deployed_at time window, capped at the latest 10 rows."""
    return select_deployments_by_time_window(deployed_from, deployed_to)
