from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.enums import AffectedService, WebhookDeliveryStatus
from app.models import (
    ApiUsageLog,
    Customer,
    Deployment,
    Incident,
    Subscription,
    SupportTeamMember,
    TicketHistory,
    WebhookDeliveryLog,
)


class WorldRow(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ApiUsageLogData(WorldRow):
    id: int
    customer_id: int
    endpoint: str
    method: str
    status_code: int
    latency_ms: int
    error_code: str | None
    created_at: datetime


class CustomerData(WorldRow):
    id: int
    company_name: str
    contact_email: str
    region: str | None
    plan: str | None
    status: str
    created_at: datetime


class DeploymentData(WorldRow):
    id: int
    service_name: str
    version: str
    environment: str
    deployed_at: datetime
    status: str
    summary: str | None
    rollback_available: bool


class IncidentData(WorldRow):
    id: int
    title: str
    affected_service: AffectedService
    status: str
    severity: str
    started_at: datetime
    resolved_at: datetime | None
    summary: str
    customer_impact: str | None


class SubscriptionData(WorldRow):
    id: int
    customer_id: int
    plan: str
    monthly_event_limit: int
    current_month_events: int
    rate_limit_per_minute: int
    sla_response_time_minutes: int
    support_tier: str
    is_over_limit: bool


class SupportTeamMemberData(WorldRow):
    id: int
    full_name: str
    email: str
    team: str
    role: str
    status: str
    created_at: datetime


class TicketHistoryData(WorldRow):
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


class WebhookDeliveryLogData(WorldRow):
    id: int
    customer_id: int
    event_type: str
    endpoint_url: str
    status_code: int | None
    delivery_status: WebhookDeliveryStatus
    attempt_count: int
    error_message: str | None
    created_at: datetime
    last_attempt_at: datetime | None


class WorldData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_usage_logs: list[ApiUsageLogData]
    customers: list[CustomerData]
    deployments: list[DeploymentData]
    incidents: list[IncidentData]
    subscriptions: list[SubscriptionData]
    support_team_members: list[SupportTeamMemberData]
    ticket_history: list[TicketHistoryData]
    webhook_delivery_logs: list[WebhookDeliveryLogData]


WORLD_MODEL_SCHEMAS = {
    ApiUsageLog: ApiUsageLogData,
    Customer: CustomerData,
    Deployment: DeploymentData,
    Incident: IncidentData,
    Subscription: SubscriptionData,
    SupportTeamMember: SupportTeamMemberData,
    TicketHistory: TicketHistoryData,
    WebhookDeliveryLog: WebhookDeliveryLogData,
}


def load_world(path: Path) -> WorldData:
    return WorldData.model_validate_json(path.read_text(encoding="utf-8"))


def validate_world_schema_matches_database_models() -> None:
    for database_model, world_schema in WORLD_MODEL_SCHEMAS.items():
        database_fields = set(database_model.__table__.columns.keys())
        schema_fields = set(world_schema.model_fields)
        if database_fields != schema_fields:
            raise ValueError(
                f"{database_model.__name__} fields do not match "
                f"{world_schema.__name__}: database={sorted(database_fields)}, "
                f"schema={sorted(schema_fields)}"
            )
