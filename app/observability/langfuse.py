from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from copy import copy
from datetime import date, datetime
from typing import Any, TypeVar

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

load_dotenv()

Langfuse(mask=lambda *, data, **_: mask_sensitive_data(data))

T = TypeVar("T")

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()/-]{7,}\d)(?!\d)")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def mask_sensitive_data(data: Any) -> Any:
    if isinstance(data, str):
        masked = EMAIL_RE.sub("[REDACTED_EMAIL]", data)
        masked = CREDIT_CARD_RE.sub("[REDACTED_CARD]", masked)
        return PHONE_RE.sub("[REDACTED_PHONE]", masked)

    if isinstance(data, Mapping):
        return {
            key: "[REDACTED]"
            if str(key).lower() in {"password", "token", "secret", "api_key"}
            else mask_sensitive_data(value)
            for key, value in data.items()
        }

    if isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]

    if isinstance(data, tuple):
        return tuple(mask_sensitive_data(item) for item in data)

    return data


def merge_langfuse_callbacks(config: RunnableConfig | None = None) -> RunnableConfig:
    merged: RunnableConfig = copy(config) if config is not None else {}
    callbacks = list(merged.get("callbacks") or [])
    callbacks.append(CallbackHandler())
    merged["callbacks"] = callbacks
    return merged


def invoke_graph_with_langfuse(
    graph: Any,
    input_data: Any,
    *,
    trace_name: str,
    config: RunnableConfig | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
    context: Any = None,
) -> T:
    langfuse = get_client()
    langfuse_config = merge_langfuse_callbacks(config)

    with langfuse.start_as_current_observation(
        as_type="span",
        name=trace_name,
    ) as span:
        span.update(
            input=_trace_input(input_data),
            metadata=mask_sensitive_data(dict(metadata or {})),
        )

        with propagate_attributes(
            trace_name=trace_name,
            session_id=session_id,
            user_id=user_id,
            tags=list(tags),
        ):
            result: T = graph.invoke(
                input_data,
                config=langfuse_config,
                context=context,
            )

        span.update(output=_trace_output(result))
        return result


def shutdown_langfuse() -> None:
    get_client().shutdown()


def _trace_input(input_data: Any) -> Any:
    if isinstance(input_data, Mapping) and "ticket" in input_data:
        return {"ticket": mask_sensitive_data(input_data.get("ticket"))}

    return mask_sensitive_data(_json_safe(input_data))


def _trace_output(result: Any) -> Any:
    return mask_sensitive_data(_json_safe(result))


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())

    return repr(value)
