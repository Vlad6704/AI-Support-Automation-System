from datetime import datetime
from enum import Enum
from typing import TypeAlias, cast

from app.models import (
    ApiUsageLog,
    Customer,
    Deployment,
    Incident,
    Invoice,
    Message,
    Subscription,
    TicketHistory,
    WebhookDeliveryLog,
    WebhookEndpoint,
)
from app.repositories.agent_repository_protocols import SerializedRow, SerializedValue


SerializableModel: TypeAlias = (
    ApiUsageLog
    | Customer
    | Deployment
    | Incident
    | Invoice
    | Message
    | Subscription
    | TicketHistory
    | WebhookDeliveryLog
    | WebhookEndpoint
)


def serialize_value(value: object) -> SerializedValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return serialize_value(value.value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [serialize_value(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        serialized: dict[str, SerializedValue] = {}
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise TypeError(f"Serialized dictionary keys must be strings, got {key!r}.")
            serialized[key] = serialize_value(item)
        return serialized
    raise TypeError(f"Unsupported serialized value type: {type(value).__name__}")


def model_to_dict(model: SerializableModel) -> SerializedRow:
    return {
        column.name: serialize_value(getattr(model, column.name))
        for column in model.__table__.columns
    }
