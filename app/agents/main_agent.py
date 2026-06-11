from datetime import datetime
import os
from pathlib import Path
from sqlite3 import connect
from typing import Annotated, Literal, TypedDict, cast

from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages import BaseMessage, MessageLikeRepresentation
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from pydantic import BaseModel

from app.agents.context import (
    AgentContext,
)
from app.agents.webhook_agent import graph as webhook_agent_graph
from app.enums import TicketStatus
from app.repositories import CustomerContextData

Intent = Literal["support", "not_support"]
SupportCategory = Literal["webhook", "other"]
GuardrailDecision = Literal["valid", "invalid"]
DraftRisk = Literal["low", "mid", "high"]
RiskDestination = Literal["support_review", "finalize_response"]
SupportReviewDestination = Literal["webhook_agent"]
ReviewCloseDestination = Literal["support_review", "finalize_response"]
WebhookDestination = Literal["estimate_risk", "close_prev_review"]


def merge_node_calls(
    left: dict[str, object] | None, right: dict[str, object] | None
) -> dict[str, object]:
    return {**(left or {}), **(right or {})}


def message_content_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(
        block if isinstance(block, str) else str(block) for block in content
    )


class CustomerData(TypedDict):
    id: int
    company_name: str
    contact_email: str
    region: str | None
    plan: str | None
    status: str
    created_at: datetime


class DraftGuardrail(TypedDict):
    decision: GuardrailDecision
    message: str


class MainAgentState(TypedDict, total=False):
    id: int
    customer_id: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: TicketStatus
    category: str | None
    updated_by: str | None
    resolution_summery: str | None
    messages: Annotated[list[BaseMessage], add_messages]
    customer: CustomerData
    customer_context: CustomerContextData
    intent: Intent
    intent_reason: str
    draft_response: str | None
    draft_guardrail: DraftGuardrail | None
    draft_risk: DraftRisk | None
    draft_review_id: int | None
    node_calls: Annotated[dict[str, object], merge_node_calls]


class IntentOutput(BaseModel):
    intent: Intent
    category: SupportCategory
    reason: str


class RiskOutput(BaseModel):
    draft_risk: DraftRisk


def node_classify_intent(
    state: MainAgentState, config: RunnableConfig | None = None
) -> MainAgentState:
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(IntentOutput)
    conversation = state.get("messages", [])
    ticket_message = (
        message_content_text(conversation[-1])
        if conversation
        else state.get("description")
    )
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "Classify whether this ticket message is related to customer support. "
            "Return intent='support' for product issues, account questions, billing, "
            "webhooks, incidents, access problems, bugs, or how-to requests. "
            "Return intent='not_support' for unrelated spam, sales outreach, or casual "
            "messages that do not require support action. "
            "Return category='webhook' when the request concerns webhook delivery, "
            "configuration, events, endpoints, retries, or failures. Return "
            "category='other' for all other requests."
        ),
        HumanMessage(f"Title: {state.get('title')}\n\nMessage: {ticket_message}"),
    ]
    result = cast(IntentOutput, structured_model.invoke(messages, config=config))
    return {
        "intent": result.intent,
        "category": result.category,
        "intent_reason": result.reason,
        "node_calls": {
            "node_classify_intent": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }


def node_close_prev_review(
    state: MainAgentState,
    runtime: Runtime[AgentContext],
) -> Command[ReviewCloseDestination]:
    review_id = state.get("draft_review_id")
    guardrail = state.get("draft_guardrail")
    if review_id is None or guardrail is None:
        raise ValueError("Closing a review requires review and guardrail data.")

    is_valid = guardrail["decision"] == "valid"
    runtime.context.draft_review_service.close_review(
        review_id,
        guardrail_feedback=None if is_valid else guardrail["message"],
    )
    destination: ReviewCloseDestination = (
        "finalize_response" if is_valid else "support_review"
    )
    return Command[ReviewCloseDestination](
        goto=destination,
        update={"draft_review_id": None},
    )


def node_estimate_draft_risk(
    state: MainAgentState,
    config: RunnableConfig | None = None,
) -> Command[RiskDestination]:
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(RiskOutput)
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "Estimate the business risk of sending a validated customer-support draft. "
            "Return draft_risk='low' for routine informational responses with no "
            "meaningful business impact. Return draft_risk='mid' for responses involving "
            "customer-impacting technical issues, ambiguous facts, or actions that may "
            "need follow-up. Return draft_risk='high' for security, privacy, legal, "
            "financial, account-access, widespread outage, or other severe concerns. "
            "Use only the provided inputs."
        ),
        HumanMessage(
            "Ticket:\n"
            f"Title: {state.get('title')}\n"
            f"Description: {state.get('description')}\n\n"
            "Retrieved/support context:\n"
            f"{state.get('customer_context') or state.get('customer')}\n\n"
            "Draft message:\n"
            f"{state.get('draft_response')}\n\n"
            "Guardrail result:\n"
            f"{state.get('draft_guardrail')}"
        ),
    ]
    result = cast(RiskOutput, structured_model.invoke(messages, config=config))
    update: MainAgentState = {
        "draft_risk": result.draft_risk,
        "node_calls": {
            "node_estimate_draft_risk": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }
    destination: RiskDestination = (
        "finalize_response" if result.draft_risk == "low" else "support_review"
    )
    return Command[RiskDestination](goto=destination, update=update)


def node_support_review(
    state: MainAgentState,
    runtime: Runtime[AgentContext],
) -> Command[SupportReviewDestination]:
    ticket_id = state.get("id")
    customer_id = state.get("customer_id")
    draft_response = (state.get("draft_response") or "").strip()
    if ticket_id is None or customer_id is None or not draft_response:
        raise ValueError("Support review requires ticket, customer, and draft data.")

    review = runtime.context.draft_review_service.get_or_create_open_review(
        ticket_id=ticket_id,
        customer_id=customer_id,
        original_draft=draft_response,
        guardrail_feedback=(state.get("draft_guardrail") or {}).get("message"),
    )
    review_input = cast(
        dict[str, str],
        interrupt(
            {
                "review_id": review.id,
                "ticket_id": ticket_id,
                "draft": draft_response,
            }
        ),
    )
    edited_draft = str(review_input.get("edited_draft") or "").strip()
    if int(review_input.get("review_id") or 0) != review.id:
        raise ValueError("Submitted review does not match the active review.")
    if not edited_draft:
        raise ValueError("Reviewed draft cannot be blank.")
    runtime.context.draft_review_service.submit_review(
        review.id,
        edited_draft=edited_draft,
        reviewer_notes=review_input.get("reviewer_notes"),
        updated_by=review_input.get("updated_by") or "support_team",
    )
    return Command[SupportReviewDestination](
        goto="webhook_agent",
        update={
            "draft_response": edited_draft,
            "draft_review_id": review.id,
        },
    )


def node_finalize_response(state: MainAgentState) -> MainAgentState:
    draft_response = (state.get("draft_response") or "").strip()
    if not draft_response:
        raise ValueError("Cannot finalize an empty draft response.")
    return {
        "messages": [AIMessage(content=draft_response)],
        "draft_response": None,
        "draft_guardrail": None,
        "draft_risk": None,
        "draft_review_id": None,
    }


def node_return_friendly_message(state: MainAgentState) -> MainAgentState:
    message = (
        "Thanks for reaching out. Webhook support is currently the only automated "
        "support category available, so this request needs to be handled by the "
        "support team."
        if state.get("intent") == "support"
        else (
            "Thanks for reaching out. This message does not look like a support request, "
            "so I do not have a ticket-specific action to take right now. If you need "
            "help with the product, your account, billing, or a technical issue, please "
            "send a few details and I will be happy to help."
        )
    )
    return {
        "draft_response": message,
        "messages": [AIMessage(content=message)],
        "node_calls": {
            "node_return_friendly_message": {
                "result": {
                    "draft_response": message,
                    "intent": state.get("intent"),
                    "intent_reason": state.get("intent_reason"),
                }
            }
        },
    }


def route_after_intent(
    state: MainAgentState,
) -> Literal["webhook_agent", "friendly_message"]:
    if state.get("intent") == "support" and state.get("category") in {
        "webhook",
        "webhooks",
    }:
        return "webhook_agent"
    return "friendly_message"


def route_after_webhook_agent(state: MainAgentState) -> WebhookDestination:
    if state.get("draft_review_id") is not None:
        return "close_prev_review"
    return "estimate_risk"


builder = StateGraph(MainAgentState, context_schema=AgentContext)
builder.add_node("classify_intent", node_classify_intent)
builder.add_node("webhook_agent", webhook_agent_graph)
builder.add_node("close_prev_review", node_close_prev_review)
builder.add_node("estimate_risk", node_estimate_draft_risk)
builder.add_node("support_review", node_support_review)
builder.add_node("finalize_response", node_finalize_response)
builder.add_node("friendly_message", node_return_friendly_message)

builder.add_edge(START, "classify_intent")
builder.add_conditional_edges("classify_intent", route_after_intent)
builder.add_conditional_edges("webhook_agent", route_after_webhook_agent)
builder.add_edge("finalize_response", END)
builder.add_edge("friendly_message", END)

CHECKPOINT_DB_PATH = Path(
    os.getenv(
        "CHECKPOINT_DATABASE_PATH",
        Path(__file__).resolve().parents[2] / "checkpoints.db",
    )
)
CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
checkpoint_connection = connect(CHECKPOINT_DB_PATH, check_same_thread=False)
checkpointer = SqliteSaver(checkpoint_connection)
graph = builder.compile(checkpointer=checkpointer)
