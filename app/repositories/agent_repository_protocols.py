from datetime import date, datetime
from typing import Literal, Protocol, TypedDict

from app.enums import AffectedService, TicketStatus, TicketSupportability


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
    status: TicketStatus
    supportability: TicketSupportability
    category: str | None
    updated_by: str | None
    resolution_summery: str | None


class InvoiceData(TypedDict):
    invoice_id: int
    start_date: str
    end_date: str
    amount: str
    refundable: bool


type SerializedScalar = str | int | float | bool | None
type SerializedValue = (
    SerializedScalar | list[SerializedValue] | dict[str, SerializedValue]
)
type SerializedRow = dict[str, SerializedValue]
type FilterScalar = SerializedScalar | date | datetime
type FilterValue = FilterScalar | list[FilterScalar]
type WhereOperator = Literal[
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


class WhereCondition(TypedDict):
    column: str
    operator: WhereOperator
    value: FilterValue


class RepositoryWhere(TypedDict):
    match: Literal["all", "any"]
    conditions: list[WhereCondition]


class QueryResult(TypedDict):
    rows: list[SerializedRow]
    count: int


class CustomerContextData(TypedDict):
    customer: SerializedRow | None
    messages: list[SerializedRow]
    subscriptions: list[SerializedRow]
    api_usage_logs: list[SerializedRow]
    ticket_history: list[SerializedRow]
    last_30_webhook_delivery_logs: list[SerializedRow]
    last_30_webhook_endpoints: list[SerializedRow]


class AgentRepository(Protocol):
    def get_customer_by_id(self, customer_id: int) -> CustomerData | None: ...

    def get_ticket_by_id(self, ticket_id: int) -> TicketHistoryData | None: ...

    def get_first_ticket(self) -> TicketHistoryData | None: ...

    def get_latest_user_message(self, ticket_id: int) -> SerializedRow | None: ...

    def get_invoice_by_id(self, invoice_id: int) -> InvoiceData | None: ...

    def get_customer_context(self, customer_id: int) -> CustomerContextData: ...

    def get_webhook_delivery_logs(
        self,
        customer_id: int,
        where: RepositoryWhere | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> QueryResult: ...

    def get_webhook_endpoints(
        self,
        customer_id: int,
        where: RepositoryWhere | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> QueryResult: ...

    def get_incidents(
        self,
        affected_service: AffectedService,
        limit: int = 20,
    ) -> list[SerializedRow]: ...

    def get_deployments(
        self,
        deployed_from: datetime | None = None,
        deployed_to: datetime | None = None,
    ) -> list[SerializedRow]: ...
