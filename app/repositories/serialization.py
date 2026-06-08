from datetime import datetime
from typing import Any


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def model_to_dict(model: Any) -> dict[str, Any]:
    return {
        column.name: serialize_value(getattr(model, column.name))
        for column in model.__table__.columns
    }
