from datetime import datetime
from typing import cast

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from app.agents.context import AgentContext
from app.enums import AffectedService
from app.repositories import CustomerContextData, SerializedRow


@tool
def select_customer_context(
    customer_id: int,
    runtime: ToolRuntime,
) -> CustomerContextData:
    """Select customer-owned data from all customer tables except support_team_members."""
    context = cast(AgentContext, runtime.context)
    return context.repository.get_customer_context(customer_id)


@tool
def select_incidents_by_affected_service(
    affected_service: AffectedService,
    runtime: ToolRuntime,
    limit: int = 20,
) -> list[SerializedRow]:
    """Select incidents for an affected service, capped at 20 rows."""
    context = cast(AgentContext, runtime.context)
    return context.repository.get_incidents(affected_service, limit)


@tool
def select_deployments(
    runtime: ToolRuntime,
    deployed_from: datetime | None = None,
    deployed_to: datetime | None = None,
) -> list[SerializedRow]:
    """Select deployments by optional deployed_at time window, capped at the latest 10 rows."""
    context = cast(AgentContext, runtime.context)
    return context.repository.get_deployments(deployed_from, deployed_to)
