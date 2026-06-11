from typing import cast

from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.messages import BaseMessage, MessageLikeRepresentation
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel

from app.agents.context import AgentContext
from app.agents.webhook_agent.state import DraftGuardrail, GuardrailDecision, WebhookAgentState


class DraftOutput(BaseModel):
    draft: str


class GuardrailOutput(BaseModel):
    guardrail_decision: GuardrailDecision
    guardrail_message: str


def message_content_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(
        block if isinstance(block, str) else str(block)
        for block in content
    )


def node_get_customer_context(
    state: WebhookAgentState,
    runtime: Runtime[AgentContext],
) -> WebhookAgentState:
    customer_id = state.get("customer_id")
    if customer_id is None:
        return {}

    return {
        "customer_context": runtime.context.repository.get_customer_context(customer_id)
    }


def node_get_draft_response(
    state: WebhookAgentState,
    config: RunnableConfig | None = None,
) -> WebhookAgentState:
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(DraftOutput)
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "You are a webhook support agent. Write a concise, helpful draft response "
            "for the ticket using the retrieved customer context."
        ),
        HumanMessage(
            "Ticket:\n"
            f"Title: {state.get('title')}\n"
            f"Description: {state.get('description')}\n\n"
            f"Conversation messages: {state.get('messages', [])}\n\n"
            f"Intent: {state.get('intent')}\n"
            f"Intent reason: {state.get('intent_reason')}\n"
            f"Customer context: {state.get('customer_context')}\n"
            f"Previous guardrail feedback: {state.get('draft_guardrail')}"
        ),
    ]
    result = cast(DraftOutput, structured_model.invoke(messages, config=config))
    return {
        "draft_response": result.draft,
        "node_calls": {
            "node_get_draft_response": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }


def node_validate_draft_response(
    state: WebhookAgentState,
    config: RunnableConfig | None = None,
) -> WebhookAgentState:
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(GuardrailOutput)
    conversation = state.get("messages", [])
    user_messages = [
        message_content_text(message)
        for message in conversation
        if isinstance(message, HumanMessage)
    ]
    user_message = user_messages[-1] if user_messages else state.get("description")
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "Validate a drafted customer-support response before it is sent. Approve "
            "the draft unless it contains a clear, material problem. Do not reject it "
            "for minor wording, style, completeness, or formatting preferences. Allow "
            "reasonable uncertainty, requests for identifiers or timestamps, references "
            "to currently unavailable records, and commitments to check or investigate "
            "once the customer provides needed details. Return guardrail_decision="
            "'invalid' only for harmful content, private-data leakage, hidden reasoning "
            "or sensitive internal details, unauthorized financial or account-action "
            "promises, clearly invented factual claims, or seriously unprofessional "
            "language. A technical field name alone is not sensitive internal leakage. "
            "When uncertain, return guardrail_decision='valid'. Set guardrail_message "
            "to a concise description of a material violation when invalid, or a short "
            "confirmation when valid."
        ),
        HumanMessage(
            "User message:\n"
            f"{user_message}\n\n"
            "Retrieved/support context:\n"
            f"{state.get('customer_context')}\n\n"
            "Draft message:\n"
            f"{state.get('draft_response')}\n\n"
            "Business policy:\n"
            "Responses must be safe, professional, and materially accurate. Reasonable "
            "requests for information and commitments to investigate are allowed.\n\n"
            "Approved actions:\n"
            "Ask for troubleshooting details, explain findings, and provide reasonable "
            "next steps. Do not promise refunds, credits, account changes, cancellations, "
            "or a specific resolution unless explicitly supported."
        ),
    ]
    result = cast(GuardrailOutput, structured_model.invoke(messages, config=config))
    draft_guardrail: DraftGuardrail = {
        "decision": result.guardrail_decision,
        "message": result.guardrail_message,
    }
    return {
        "draft_guardrail": draft_guardrail,
        "node_calls": {
            "node_validate_draft_response": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }
