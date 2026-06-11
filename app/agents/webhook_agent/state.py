from datetime import datetime
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage

from app.enums import TicketStatus
from app.repositories import CustomerContextData

GuardrailDecision = Literal["valid", "invalid"]


def merge_node_calls(
    left: dict[str, object] | None, right: dict[str, object] | None
) -> dict[str, object]:
    return {**(left or {}), **(right or {})}


class DraftGuardrail(TypedDict):
    decision: GuardrailDecision
    message: str


class WebhookAgentState(TypedDict, total=False):
    id: int
    customer_id: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: TicketStatus
    messages: list[BaseMessage]
    customer_context: CustomerContextData
    investigation_result: str
    intent: str
    intent_reason: str
    draft_response: str | None
    draft_guardrail: DraftGuardrail | None
    draft_review_id: int | None
    node_calls: Annotated[dict[str, object], merge_node_calls]
