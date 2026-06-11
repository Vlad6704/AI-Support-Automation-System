from datetime import datetime
from typing import Annotated, Literal, TypeAlias, cast

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.agents.context import AgentContext
from app.enums import AffectedService
from app.repositories import (
    CustomerContextData,
    QueryResult,
    SerializedRow,
)

AgentToolRuntime = ToolRuntime[object, dict[str, object]]
ToolLimit = Annotated[
    int,
    Field(
        ge=1,
        le=100,
        description="Maximum rows to return. Use offset to retrieve additional pages.",
    ),
]
ToolOffset = Annotated[
    int,
    Field(
        ge=0,
        description="Number of matching rows to skip before returning results.",
    ),
]
WhereValue: TypeAlias = (
    str
    | int
    | bool
    | datetime
    | list[str | int | bool | datetime]
    | None
)
WhereOperator = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "contains",
    "starts_with",
    "ends_with",
    "is_null",
    "is_not_null",
]


class WebhookDeliveryLogCondition(BaseModel):
    """One SQL-like condition for webhook delivery logs."""

    model_config = ConfigDict(extra="forbid")

    column: Literal[
        "id",
        "event_type",
        "webhook_endpoint_id",
        "status_code",
        "delivery_status",
        "attempt_count",
        "error_message",
        "created_at",
        "last_attempt_at",
    ] = Field(description="Delivery-log column to compare. customer_id is unavailable.")
    operator: WhereOperator = Field(
        description=(
            "Comparison operator. Use gte/lte for ranges, in/not_in for lists, "
            "and is_null/is_not_null without a value."
        )
    )
    value: WhereValue = Field(
        default=None,
        description=(
            "Comparison value. Use an ISO 8601 timestamp for datetime columns and "
            "a list for in/not_in."
        ),
    )


class WebhookDeliveryLogWhere(BaseModel):
    """SQL-like where clause for webhook delivery-log queries."""

    model_config = ConfigDict(extra="forbid")

    match: Literal["all", "any"] = Field(
        default="all",
        description="Use all for SQL AND semantics or any for SQL OR semantics.",
    )
    conditions: list[WebhookDeliveryLogCondition] = Field(
        default_factory=list,
        description="Conditions to apply. An empty list selects all ticket-customer rows.",
    )


class WebhookEndpointCondition(BaseModel):
    """One SQL-like condition for webhook endpoints."""

    model_config = ConfigDict(extra="forbid")

    column: Literal["id", "url", "events", "status", "created_at"] = Field(
        description="Endpoint column to compare. customer_id is unavailable."
    )
    operator: WhereOperator = Field(
        description=(
            "Comparison operator. Use gte/lte for ranges, in/not_in for lists, "
            "and is_null/is_not_null without a value."
        )
    )
    value: WhereValue = Field(
        default=None,
        description=(
            "Comparison value. Use an ISO 8601 timestamp for created_at and a list "
            "for in/not_in."
        ),
    )


class WebhookEndpointWhere(BaseModel):
    """SQL-like where clause for webhook endpoint queries."""

    model_config = ConfigDict(extra="forbid")

    match: Literal["all", "any"] = Field(
        default="all",
        description="Use all for SQL AND semantics or any for SQL OR semantics.",
    )
    conditions: list[WebhookEndpointCondition] = Field(
        default_factory=list,
        description="Conditions to apply. An empty list selects all ticket-customer rows.",
    )


def _agent_context(runtime: AgentToolRuntime) -> AgentContext:
    return cast(AgentContext, runtime.context)


def _ticket_customer_id(runtime: AgentToolRuntime) -> int:
    customer_id = runtime.state.get("customer_id")
    if not isinstance(customer_id, int):
        raise ValueError("Webhook query tools require a ticket customer_id in state.")
    return customer_id


@tool
def select_customer_context(
    customer_id: int,
    runtime: AgentToolRuntime,
) -> CustomerContextData:
    """Select customer-owned data from all customer tables except support_team_members."""
    return _agent_context(runtime).repository.get_customer_context(customer_id)


@tool
def select_incidents_by_affected_service(
    affected_service: AffectedService,
    runtime: AgentToolRuntime,
    limit: int = 20,
) -> list[SerializedRow]:
    """Select incidents for an affected service, capped at 20 rows."""
    return _agent_context(runtime).repository.get_incidents(affected_service, limit)


@tool
def select_deployments(
    runtime: AgentToolRuntime,
    deployed_from: datetime | None = None,
    deployed_to: datetime | None = None,
) -> list[SerializedRow]:
    """Select deployments by optional deployed_at time window, capped at the latest 10 rows."""
    return _agent_context(runtime).repository.get_deployments(deployed_from, deployed_to)


@tool
def select_webhook_delivery_logs(
    runtime: AgentToolRuntime,
    where: WebhookDeliveryLogWhere | None = None,
    limit: ToolLimit = 50,
    offset: ToolOffset = 0,
) -> QueryResult | str:
    """Query and count this ticket customer's webhook delivery logs.

    Use SQL-like where conditions for comparisons, ranges, lists, null checks, and
    string matching. customer_id is always taken from the active ticket.
    """
    customer_id = _ticket_customer_id(runtime)
    try:
        return _agent_context(runtime).repository.get_webhook_delivery_logs(
            customer_id,
            where.model_dump() if where is not None else None,
            limit,
            offset,
        )
    except ValueError as error:
        return f"Invalid webhook delivery-log query: {error}"


@tool
def select_webhook_endpoints(
    runtime: AgentToolRuntime,
    where: WebhookEndpointWhere | None = None,
    limit: ToolLimit = 50,
    offset: ToolOffset = 0,
) -> QueryResult | str:
    """Query and count this ticket customer's webhook endpoints.

    Use SQL-like where conditions for comparisons, ranges, lists, null checks, and
    string matching. customer_id is always taken from the active ticket.
    """
    customer_id = _ticket_customer_id(runtime)
    try:
        return _agent_context(runtime).repository.get_webhook_endpoints(
            customer_id,
            where.model_dump() if where is not None else None,
            limit,
            offset,
        )
    except ValueError as error:
        return f"Invalid webhook endpoint query: {error}"
