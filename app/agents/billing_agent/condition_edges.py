from typing import Literal

from app.agents.billing_agent.state import SupportState


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
