from typing import Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.messages import MessageLikeRepresentation
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from langsmith import Client
from pydantic import BaseModel

from app.agents.billing_agent.state import BillingSubcategory, Category, SupportState

load_dotenv()
client = Client()


class CategoryOutput(BaseModel):
    category: Category
    billing_subcategory: BillingSubcategory


class DraftOutput(BaseModel):
    draft: str


class BillingDataOutput(BaseModel):
    invoice_id: int | None


class BillingDataRequestOutput(BaseModel):
    message: str


class InvoiceDateOutput(BaseModel):
    date_type: Literal["start", "end", "both"]


class MockInvoice(TypedDict):
    invoice_id: int
    start_date: str
    end_date: str
    amount: str
    refundable: bool


MOCK_INVOICES: list[MockInvoice] = [
    {
        "invoice_id": 1001,
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "amount": "$49.00",
        "refundable": True,
    },
    {
        "invoice_id": 1002,
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "amount": "$49.00",
        "refundable": False,
    },
    {
        "invoice_id": 1003,
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
        "amount": "$79.00",
        "refundable": True,
    },
]


def _find_mock_invoice(invoice_id: int | None) -> MockInvoice | None:
    if invoice_id is None:
        return None

    for invoice in MOCK_INVOICES:
        if invoice["invoice_id"] == invoice_id:
            return invoice
    return None


def node_classify_ticket(
    state: SupportState, config: RunnableConfig | None = None
) -> SupportState:
    ticket = state.get("ticket")
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(CategoryOutput)
    prompt = client.pull_prompt("node_classify_ticket")
    chain = prompt | structured_model
    result: CategoryOutput = cast(
        CategoryOutput, chain.invoke({"ticket": ticket}, config=config)
    )
    category = result.category
    return {
        "category": category,
        "billing_subcategory": result.billing_subcategory,
        "node_calls": {
            "node_classify_ticket": {
                "messages": prompt,
                "result": result.model_dump(),
            }
        },
    }


def node_ask_fot_billing_data(
    state: SupportState, config: RunnableConfig | None = None
) -> SupportState:
    ticket = state.get("ticket")
    category = state.get("category")
    invoice_id = state.get("billing_data", {}).get("invoice_id")
    model = init_chat_model(model="openai:gpt-5.4-nano")
    billing_data_model = model.with_structured_output(BillingDataOutput)
    initial_extraction_messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "Extract the invoice id from the user's ticket. If there is no invoice id, "
            "return null for invoice_id."
        ),
        HumanMessage(str(ticket)),
    ]
    billing_data = cast(
        BillingDataOutput,
        billing_data_model.invoke(initial_extraction_messages, config=config),
    )

    if billing_data.invoice_id is not None:
        return {
            "billing_data": {"invoice_id": billing_data.invoice_id},
            "node_calls": {
                "node_ask_fot_billing_data": {
                    "messages": initial_extraction_messages,
                    "result": {
                        "billing_data": billing_data.model_dump(),
                        "source": "ticket",
                    },
                }
            },
        }

    messages: list[MessageLikeRepresentation] = [
        SystemMessage("Ask user to provide invoice id"),
        HumanMessage(
            f"Ticket: {ticket}, Category: {category}, Invoice id: {invoice_id}"
        ),
    ]
    structured_model = model.with_structured_output(BillingDataRequestOutput)
    request_result = cast(
        BillingDataRequestOutput, structured_model.invoke(messages, config=config)
    )
    user_reply = interrupt(request_result.message)
    extraction_messages: list[MessageLikeRepresentation] = [
        SystemMessage("Extract the invoice id from the user's message."),
        HumanMessage(str(user_reply)),
    ]
    billing_data = cast(
        BillingDataOutput,
        billing_data_model.invoke(extraction_messages, config=config),
    )
    return {
        "billing_data": {"invoice_id": billing_data.invoice_id},
        "node_calls": {
            "node_ask_fot_billing_data": {
                "messages": messages + extraction_messages,
                "result": {
                    "request": request_result.model_dump(),
                    "billing_data": billing_data.model_dump(),
                },
            }
        },
    }


def node_get_draft_response(
    state: SupportState, config: RunnableConfig | None = None
) -> SupportState:
    ticket = state.get("ticket")
    category = state.get("category")
    billing_subcategory = state.get("billing_subcategory")
    invoice_id = state.get("billing_data", {}).get("invoice_id")
    billing_context = state.get("billing_context")

    model = init_chat_model(model="openai:gpt-5.4-nano")
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "You are a support worker. Consider ticket and category and write short "
            "draft for ticket response"
        ),
        HumanMessage(
            f"Ticket: {ticket}, Category: {category}, "
            f"Billing subcategory: {billing_subcategory}, Invoice id: {invoice_id}, "
            f"Billing context: {billing_context}"
        ),
    ]
    structured_model = model.with_structured_output(DraftOutput)
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


def node_get_invoice_date(
    state: SupportState, config: RunnableConfig | None = None
) -> SupportState:
    ticket = state.get("ticket")
    invoice_id = state.get("billing_data", {}).get("invoice_id")
    invoice = _find_mock_invoice(invoice_id)
    model = init_chat_model(model="openai:gpt-5.4-nano")
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "Decide which invoice date the user needs. Return 'start' if they ask "
            "for a start/from/beginning date, 'end' if they ask for an end/to/until "
            "date, or 'both' if they ask generally or ask for both."
        ),
        HumanMessage(f"Ticket: {ticket}"),
    ]
    structured_model = model.with_structured_output(InvoiceDateOutput)
    date_result = cast(
        InvoiceDateOutput, structured_model.invoke(messages, config=config)
    )

    if invoice is None:
        billing_context = f"No invoice found for invoice id {invoice_id}."
    elif date_result.date_type == "end":
        billing_context = f"Invoice {invoice_id} end date is {invoice['end_date']}."
    elif date_result.date_type == "start":
        billing_context = f"Invoice {invoice_id} start date is {invoice['start_date']}."
    else:
        billing_context = (
            f"Invoice {invoice_id} starts on {invoice['start_date']} "
            f"and ends on {invoice['end_date']}."
        )

    return {
        "billing_context": billing_context,
        "node_calls": {
            "node_get_invoice_date": {
                "messages": messages,
                "result": {
                    "invoice_id": invoice_id,
                    "invoice": invoice,
                    "date_decision": date_result.model_dump(),
                    "billing_context": billing_context,
                },
            }
        },
    }


def node_check_refund(state: SupportState) -> SupportState:
    billing_subcategory = state.get("billing_subcategory")
    invoice_id = state.get("billing_data", {}).get("invoice_id")
    invoice = _find_mock_invoice(invoice_id)

    if billing_subcategory != "invoice refund":
        billing_context = (
            f"Refund check skipped: billing subcategory is {billing_subcategory}."
        )
    elif invoice is None:
        billing_context = (
            f"Refund check failed: invoice id {invoice_id} does not match any invoice."
        )
    elif invoice["refundable"]:
        billing_context = (
            f"Refund check passed: invoice {invoice_id} matches a invoice "
            f"and is refundable for {invoice['amount']}."
        )
    else:
        billing_context = (
            f"Refund check failed: invoice {invoice_id} matches a invoice "
            "but is not refundable."
        )

    return {
        "billing_context": billing_context,
        "node_calls": {
            "node_check_refund": {
                "result": {
                    "billing_subcategory": billing_subcategory,
                    "invoice_id": invoice_id,
                    "invoice": invoice,
                    "billing_context": billing_context,
                }
            }
        },
    }
