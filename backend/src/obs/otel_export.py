"""OpenTelemetry export. Span and trace ids are hashes of stable session and event ids."""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("obs.otel")


@dataclass
class ExportSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_unix_nano: int
    end_unix_nano: int
    status_code: str
    attributes: dict[str, str | int | float | bool] = field(default_factory=dict)


def stable_id(seed: str, nbytes: int) -> str:
    raw = bytearray(hashlib.sha256(seed.encode()).digest()[:nbytes])
    if all(byte == 0 for byte in raw):
        raw[-1] = 1
    return raw.hex()


def build_spans(session: dict, events: list[dict], *, include_content: bool) -> list[ExportSpan]:
    if not events:
        return []
    trace_id = stable_id(f"session:{session['id']}", 16)
    root_span_id = stable_id(f"session-root:{session['id']}", 8)
    start = _ts(events[0].get("ts"))
    end = _ts(events[-1].get("ts"))
    if end < start:
        end = start
    root_attrs: dict[str, str | int | float | bool] = {
        "obs.agent": session["agent"],
        "obs.project_name": session.get("project_name") or "",
        "obs.event_kind": "session",
    }
    if session.get("models"):
        root_attrs["obs.model"] = session["models"][-1]
    if session.get("parent_session_id"):
        root_attrs["obs.parent_session_id"] = session["parent_session_id"]
    if session.get("est_cost_usd") is not None:
        root_attrs["obs.est_cost_usd"] = session["est_cost_usd"]
    spans = [
        ExportSpan(
            trace_id=trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            name="session",
            start_unix_nano=start,
            end_unix_nano=max(end, start + 1_000_000),
            status_code="OK",
            attributes=root_attrs,
        )
    ]
    results = {
        event["tool_call_id"]: event
        for event in events
        if event["kind"] == "tool_result" and event.get("tool_call_id")
    }
    consumed: set[str] = set()
    for event in events:
        if event["kind"] == "tool_result" and event.get("tool_call_id") in {e.get("tool_call_id") for e in events if e["kind"] == "tool_call"}:
            continue
        if event["kind"] not in {"message", "thinking", "tool_call", "tool_result"}:
            continue
        if event["role"] == "system":
            continue
        result = None
        status = "OK"
        end_ts = _ts(event.get("ts"))
        name = f"{event['role']} message" if event["kind"] == "message" else event["kind"]
        if event["kind"] in {"tool_call", "tool_result"}:
            name = f"tool {event.get('tool_name') or 'tool'}"
            result = event if event["kind"] == "tool_result" else results.get(event.get("tool_call_id"))
            if result is not None:
                consumed.add(event.get("tool_call_id") or "")
                end_ts = _ts(result.get("ts"))
                if result.get("is_error"):
                    status = "ERROR"
            if event.get("is_error"):
                status = "ERROR"
        if end_ts < _ts(event.get("ts")):
            end_ts = _ts(event.get("ts"))
        attrs: dict[str, str | int | float | bool] = {
            "obs.agent": session["agent"],
            "obs.project_name": session.get("project_name") or "",
            "obs.event_kind": event["kind"],
        }
        if event.get("model"):
            attrs["obs.model"] = event["model"]
        if event.get("tool_name"):
            attrs["obs.tool_name"] = event["tool_name"]
        usage = event.get("usage") or {}
        if usage.get("input_tokens") is not None:
            attrs["obs.tokens_in"] = usage["input_tokens"]
        if usage.get("output_tokens") is not None:
            attrs["obs.tokens_out"] = usage["output_tokens"]
        if usage.get("cache_read_tokens") is not None:
            attrs["obs.tokens_cache_read"] = usage["cache_read_tokens"]
        if usage.get("cache_write_tokens") is not None:
            attrs["obs.tokens_cache_write"] = usage["cache_write_tokens"]
        outside = any(item.get("outside") and not item.get("dismissed") for item in event.get("paths") or [])
        if outside:
            attrs["obs.path_outside_cwd"] = True
        if include_content:
            if event.get("text"):
                attrs["obs.content.text"] = event["text"]
            if event.get("tool_input") is not None:
                attrs["obs.content.tool_input"] = json.dumps(event["tool_input"])[:8000]
            output = event.get("tool_output_preview")
            if result and result.get("tool_output_preview"):
                output = result.get("tool_output_preview")
            if output:
                attrs["obs.content.tool_output"] = output
        spans.append(
            ExportSpan(
                trace_id=trace_id,
                span_id=stable_id(f"event:{event['id']}", 8),
                parent_span_id=root_span_id,
                name=name,
                start_unix_nano=_ts(event.get("ts")),
                end_unix_nano=max(end_ts, _ts(event.get("ts")) + 1_000_000),
                status_code=status,
                attributes=attrs,
            )
        )
    return spans


def encode(spans: list[ExportSpan], protocol: str) -> tuple[bytes, str]:
    if protocol == "http/json":
        return _encode_json(spans), "application/json"
    return _encode_protobuf(spans), "application/x-protobuf"


def export_payload(
    sessions: list[tuple[dict, list[dict]]],
    *,
    include_content: bool,
    protocol: str,
) -> tuple[bytes, str] | None:
    spans: list[ExportSpan] = []
    for session, events in sessions:
        spans.extend(build_spans(session, events, include_content=include_content))
    if not spans:
        return None
    return encode(spans, protocol)


def send(endpoint: str, payload: bytes, content_type: str, timeout: float = 3.0) -> None:
    url = endpoint.rstrip("/")
    if not url.endswith("/v1/traces"):
        url += "/v1/traces"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def _ts(value: str | None) -> int:
    if not value:
        return 0
    from datetime import datetime

    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0
    return int(parsed.timestamp() * 1_000_000_000)


def _encode_json(spans: list[ExportSpan]) -> bytes:
    body = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [_kv("service.name", "obs")],
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "obs"},
                        "spans": [_span_json(span) for span in spans],
                    }
                ],
            }
        ]
    }
    return json.dumps(body).encode()


def _span_json(span: ExportSpan) -> dict:
    status = 1 if span.status_code == "OK" else 2
    data = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "name": span.name,
        "startTimeUnixNano": str(span.start_unix_nano),
        "endTimeUnixNano": str(span.end_unix_nano),
        "attributes": [_kv(key, value) for key, value in span.attributes.items()],
        "status": {"code": status},
    }
    if span.parent_span_id:
        data["parentSpanId"] = span.parent_span_id
    return data


def _kv(key: str, value) -> dict:
    if isinstance(value, bool):
        wrapped = {"boolValue": value}
    elif isinstance(value, int):
        wrapped = {"intValue": value}
    elif isinstance(value, float):
        wrapped = {"doubleValue": value}
    else:
        wrapped = {"stringValue": str(value)}
    return {"key": key, "value": wrapped}


def _encode_protobuf(spans: list[ExportSpan]) -> bytes:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
    from opentelemetry.proto.resource.v1.resource_pb2 import Resource

    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.CopyFrom(
        Resource(attributes=[KeyValue(key="service.name", value=AnyValue(string_value="obs"))])
    )
    scope = resource_spans.scope_spans.add()
    scope.scope.name = "obs"
    for span in spans:
        proto = scope.spans.add()
        proto.trace_id = bytes.fromhex(span.trace_id)
        proto.span_id = bytes.fromhex(span.span_id)
        if span.parent_span_id:
            proto.parent_span_id = bytes.fromhex(span.parent_span_id)
        proto.name = span.name
        proto.start_time_unix_nano = span.start_unix_nano
        proto.end_time_unix_nano = span.end_unix_nano
        proto.status.code = 1 if span.status_code == "OK" else 2
        for key, value in span.attributes.items():
            proto.attributes.add().CopyFrom(_proto_kv(key, value, AnyValue, KeyValue))
    return request.SerializeToString()


def _proto_kv(key: str, value, any_value_cls, key_value_cls):
    if isinstance(value, bool):
        wrapped = any_value_cls(bool_value=value)
    elif isinstance(value, int):
        wrapped = any_value_cls(int_value=value)
    elif isinstance(value, float):
        wrapped = any_value_cls(double_value=value)
    else:
        wrapped = any_value_cls(string_value=str(value))
    return key_value_cls(key=key, value=wrapped)


class ExportError(Exception):
    pass


def deliver(endpoint: str, payload: bytes, content_type: str, sender=None) -> None:
    try:
        if sender is not None:
            sender(endpoint, payload, content_type)
        else:
            send(endpoint, payload, content_type)
    except (urllib.error.URLError, TimeoutError, OSError, ExportError) as exc:
        raise ExportError(str(exc)) from exc
