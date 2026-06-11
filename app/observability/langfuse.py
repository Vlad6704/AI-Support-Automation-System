from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from copy import copy
from datetime import date, datetime
from typing import Any, Protocol, TypeAlias, TypeGuard, cast, runtime_checkable

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackManager
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

load_dotenv()


def _langfuse_mask(*, data: Any, **_: dict[str, Any]) -> object:
    return mask_sensitive_data(data)


Langfuse(mask=_langfuse_mask)

MetadataValue: TypeAlias = str | int | float | bool | None
TraceMetadata: TypeAlias = Mapping[str, MetadataValue]

AGENT_VERSION = os.getenv("AGENT_VERSION", "0.1.0")

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()/-]{7,}\d)(?!\d)")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
ISO_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]|$)")


def mask_sensitive_data(data: object) -> object:
    if isinstance(data, str):
        return _mask_sensitive_string(data)

    if isinstance(data, Mapping):
        return {
            key: "[REDACTED]"
            if str(key).lower() in {"password", "token", "secret", "api_key"}
            else mask_sensitive_data(value)
            for key, value in cast(Mapping[object, object], data).items()
        }

    if isinstance(data, list):
        return [mask_sensitive_data(item) for item in cast(list[object], data)]

    if isinstance(data, tuple):
        return tuple(
            mask_sensitive_data(item) for item in cast(tuple[object, ...], data)
        )

    return data


def _mask_sensitive_string(value: str) -> str:
    masked = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    masked = CREDIT_CARD_RE.sub("[REDACTED_CARD]", masked)
    return PHONE_RE.sub(_mask_phone_candidate, masked)


def _mask_phone_candidate(match: re.Match[str]) -> str:
    candidate = match.group(0)
    if ISO_DATE_PREFIX_RE.match(candidate):
        return candidate
    digit_count = sum(character.isdigit() for character in candidate)
    return "[REDACTED_PHONE]" if digit_count >= 9 else candidate


def merge_langfuse_callbacks(config: RunnableConfig | None = None) -> RunnableConfig:
    merged: RunnableConfig = copy(config) if config is not None else {}
    configured_callbacks = merged.get("callbacks")
    if isinstance(configured_callbacks, BaseCallbackManager):
        callbacks = list(configured_callbacks.handlers)
    else:
        callbacks = list(configured_callbacks or [])
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
    metadata: TraceMetadata | None = None,
    context: Any = None,
) -> Any:
    langfuse = get_client()
    langfuse_config = merge_langfuse_callbacks(config)
    trace_metadata = _trace_metadata(metadata)

    with langfuse.start_as_current_observation(
        as_type="span",
        name=trace_name,
    ) as span:
        span.update(
            input=_trace_input(input_data),
            metadata=trace_metadata,
        )

        with propagate_attributes(
            trace_name=trace_name,
            session_id=session_id,
            user_id=user_id,
            tags=list(tags),
        ):
            result = graph.invoke(
                input_data,
                config=langfuse_config,
                context=context,
            )

        span.update(
            output=_trace_output(result),
            metadata=_trace_metadata(trace_metadata, result),
        )
        return result


def shutdown_langfuse() -> None:
    get_client().shutdown()


def _trace_input(input_data: object) -> object:
    if _is_string_object_mapping(input_data) and "ticket" in input_data:
        return {"ticket": mask_sensitive_data(input_data.get("ticket"))}

    return mask_sensitive_data(_json_safe(input_data))


def _trace_output(result: object) -> object:
    return mask_sensitive_data(_json_safe(result))


def _trace_metadata(
    metadata: TraceMetadata | None,
    result: object | None = None,
) -> dict[str, MetadataValue]:
    enriched = dict(metadata or {})
    enriched.setdefault("agent_version", AGENT_VERSION)
    if _is_string_object_mapping(result):
        category = result.get("category")
        if isinstance(category, str):
            enriched["category"] = category

        risk = result.get("draft_risk") or _node_result_value(
            result,
            node_name="node_estimate_draft_risk",
            key="draft_risk",
        )
        if isinstance(risk, str):
            enriched["risk"] = risk

    return _mask_trace_metadata(enriched)


def _mask_trace_metadata(
    metadata: Mapping[str, MetadataValue],
) -> dict[str, MetadataValue]:
    return {
        key: (
            "[REDACTED]"
            if key.lower() in {"password", "token", "secret", "api_key"}
            else _mask_sensitive_string(value)
            if isinstance(value, str)
            else value
        )
        for key, value in metadata.items()
    }


def _node_result_value(
    result: object,
    *,
    node_name: str,
    key: str,
) -> object:
    if not _is_string_object_mapping(result):
        return None
    node_calls = result.get("node_calls")
    if not _is_string_object_mapping(node_calls):
        return None
    node_call = node_calls.get(node_name)
    if not _is_string_object_mapping(node_call):
        return None
    node_result = node_call.get("result")
    if not _is_string_object_mapping(node_result):
        return None
    return node_result.get(key)


def _is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not isinstance(value, Mapping):
        return False
    return all(isinstance(key, str) for key in cast(Mapping[object, object], value))


@runtime_checkable
class ModelDumpable(Protocol):
    def model_dump(self) -> object: ...


def _json_safe(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in cast(Mapping[object, object], value).items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in cast(Iterable[object], value)]

    if isinstance(value, ModelDumpable):
        return _json_safe(value.model_dump())

    return repr(value)
