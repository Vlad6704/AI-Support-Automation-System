from typing import Annotated, Any, Literal, TypedDict, cast
from pydantic import BaseModel
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.messages import MessageLikeRepresentation
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.graph.message import Messages
from langgraph.types import Command, interrupt
from langsmith import Client

from IPython.display import Image, display

from rich import print
from dotenv import load_dotenv


load_dotenv()
client = Client()

Category = Literal["billing", "technical", "account", "unknown"]
BillingSubcategory = Literal["invoice basic information", "invoice refund", "unknown"]


class NodeCall(TypedDict, total=False):
    messages: list[MessageLikeRepresentation]
    result: dict[str, Any]


NodeCalls = dict[str, NodeCall]


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


def _message_list(messages: Messages) -> list[MessageLikeRepresentation]:
    if isinstance(messages, list):
        return cast(list[MessageLikeRepresentation], messages)
    return [messages]


def merge_node_calls(left: NodeCalls | None, right: NodeCalls | None) -> NodeCalls:
    merged = dict(left or {})
    for node, call in (right or {}).items():
        if node in merged and "messages" in call:
            previous_messages = merged[node].get("messages", [])
            merged[node]["messages"] = _message_list(
                add_messages(previous_messages, call["messages"])
            )
            if "result" in call:
                merged[node]["result"] = call["result"]
        else:
            merged[node] = call
    return merged


class BillingData(TypedDict, total=False):
    invoice_id: int


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


# class Action(TypedDict, total=False):
#     type: Literal["output_message"]
#     message: str


class SupportState(TypedDict, total=False):
    ticket: str
    category: Category
    billing_subcategory: BillingSubcategory
    risk_level: Literal["low", "high"]
    node_calls: Annotated[NodeCalls, merge_node_calls]
    draft_response: str
    billing_data: BillingData
    billing_context: str


def _find_mock_invoice(invoice_id: int | None) -> MockInvoice | None:
    if invoice_id is None:
        return None

    for invoice in MOCK_INVOICES:
        if invoice["invoice_id"] == invoice_id:
            return invoice
    return None


def node_classify_ticket(state: SupportState) -> SupportState:
    ticket = state.get("ticket")
    model = init_chat_model(model="openai:gpt-5.4-nano")
    structured_model = model.with_structured_output(CategoryOutput)
    prompt = client.pull_prompt(
        "node_classify_ticket",
    )
    # messages: list[MessageLikeRepresentation] = [
    #     SystemMessage(
    #         "You are a ticket categorizer. Consider ticket and return the proper "
    #         "category and billing subcategory. Billing subcategory must be "
    #         "'invoice basic information' for invoice details like start/end dates, "
    #         "'invoice refund' for refund requests, or 'unknown' when neither applies."
    #     ),
    #     HumanMessage(ticket),
    # ]
    chain = prompt | structured_model
    result: CategoryOutput = cast(CategoryOutput, chain.invoke({"ticket": ticket}))
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


def node_ask_fot_billing_data(state: SupportState) -> SupportState:
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
        BillingDataOutput, billing_data_model.invoke(initial_extraction_messages)
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
    request_result = cast(BillingDataRequestOutput, structured_model.invoke(messages))
    user_reply = interrupt(request_result.message)
    extraction_messages: list[MessageLikeRepresentation] = [
        SystemMessage("Extract the invoice id from the user's message."),
        HumanMessage(str(user_reply)),
    ]
    billing_data = cast(
        BillingDataOutput, billing_data_model.invoke(extraction_messages)
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


def node_get_draft_response(state: SupportState) -> SupportState:
    ticket = state.get("ticket")
    category = state.get("category")
    billing_subcategory = state.get("billing_subcategory")
    invoice_id = state.get("billing_data", {}).get("invoice_id")
    billing_context = state.get("billing_context")

    model = init_chat_model(model="openai:gpt-5.4-nano")
    messages: list[MessageLikeRepresentation] = [
        SystemMessage(
            "You are a support worker. Consider ticket and category and write short draft for ticket response"
        ),
        HumanMessage(
            f"Ticket: {ticket}, Category: {category}, "
            f"Billing subcategory: {billing_subcategory}, Invoice id: {invoice_id}, "
            f"Billing context: {billing_context}"
        ),
    ]
    structured_model = model.with_structured_output(DraftOutput)
    result = cast(DraftOutput, structured_model.invoke(messages))
    return {
        "draft_response": result.draft,
        "node_calls": {
            "node_get_draft_response": {
                "messages": messages,
                "result": result.model_dump(),
            }
        },
    }


def node_get_invoice_date(state: SupportState) -> SupportState:
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
    date_result = cast(InvoiceDateOutput, structured_model.invoke(messages))

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


def route_get_route(
    state: SupportState,
) -> Literal[
    "ask_for_billing_data", "get_invoice_date", "check_refund", "get_draft_response"
]:
    category = state.get("category")

    if category == "billing":
        billing_data = state.get("billing_data", {})
        if billing_data.get("invoice_id") is None:
            return "ask_for_billing_data"
        return route_after_billing_data(state)

    return "get_draft_response"


def route_after_billing_data(
    state: SupportState,
) -> Literal["get_invoice_date", "check_refund", "get_draft_response"]:
    billing_subcategory = state.get("billing_subcategory")

    if billing_subcategory == "invoice basic information":
        return "get_invoice_date"
    if billing_subcategory == "invoice refund":
        return "check_refund"

    return "get_draft_response"


builder = StateGraph(SupportState)
builder.add_node("classify_ticket", node_classify_ticket)
builder.add_node("get_draft_response", node_get_draft_response)
builder.add_node("ask_for_billing_data", node_ask_fot_billing_data)
builder.add_node("get_invoice_date", node_get_invoice_date)
builder.add_node("check_refund", node_check_refund)

builder.add_edge(START, "classify_ticket")
builder.add_conditional_edges("classify_ticket", route_get_route)
builder.add_conditional_edges("ask_for_billing_data", route_after_billing_data)
builder.add_edge("get_invoice_date", "get_draft_response")
builder.add_edge("check_refund", "get_draft_response")
builder.add_edge("get_draft_response", END)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "ticket-1"}}
    user_input = input("Input: ")
    result = graph.invoke({"ticket": user_input}, config=config)
    if result.get("__interrupt__") is not None:
        print(result.get("__interrupt__")[0].value)
        user_input = input("> ")
        result = graph.invoke(Command(resume=user_input), config=config)
    print(result)
