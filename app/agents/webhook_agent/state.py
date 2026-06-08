from typing import TypedDict

from app.repositories import CustomerContextData


class WebhookAgentState(TypedDict, total=False):
    customer_id: int
    customer_context: CustomerContextData
