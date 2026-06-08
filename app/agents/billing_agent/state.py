from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import MessageLikeRepresentation
from langgraph.graph import add_messages
from langgraph.graph.message import Messages

Category = Literal["billing", "technical", "account", "unknown"]
BillingSubcategory = Literal["invoice basic information", "invoice refund", "unknown"]


class NodeCall(TypedDict, total=False):
    messages: list[MessageLikeRepresentation]
    result: dict[str, Any]


NodeCalls = dict[str, NodeCall]


class BillingData(TypedDict, total=False):
    invoice_id: int


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


class SupportState(TypedDict, total=False):
    ticket: str
    category: Category
    billing_subcategory: BillingSubcategory
    risk_level: Literal["low", "high"]
    node_calls: Annotated[NodeCalls, merge_node_calls]
    draft_response: str
    billing_data: BillingData
    billing_context: str
