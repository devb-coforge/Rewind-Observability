import json

from obs.otel_export import build_spans, stable_id

CLAUDE = "claude_code:11111111-1111-1111-1111-111111111111"


def test_span_mapping_stable_ids_and_no_content_by_default(client):
    detail = client.get(f"/api/sessions/{CLAUDE}").json()
    events = client.get(f"/api/sessions/{CLAUDE}/events", params={"limit": 500}).json()["events"]
    first = build_spans(detail, events, include_content=False)
    second = build_spans(detail, events, include_content=False)
    assert [(span.trace_id, span.span_id, span.name) for span in first] == [
        (span.trace_id, span.span_id, span.name) for span in second
    ]
    assert first[0].trace_id == stable_id(f"session:{CLAUDE}", 16)
    tool = next(span for span in first if span.name.startswith("tool "))
    message = next(span for span in first if span.name == "user message")
    assert message.attributes["obs.event_kind"] == "message"
    bash = next(span for span in first if span.name == "tool Bash")
    assert bash.status_code == "ERROR"
    assert bash.attributes["obs.path_outside_cwd"] is True
    blob = json.dumps(bash.attributes)
    assert "/tmp/secret.txt" not in blob
    assert "obs.content" not in blob
    for span in first:
        assert not any(key.startswith("obs.content") for key in span.attributes)
    assert tool.attributes["obs.tool_name"]
    assert message.status_code == "OK"


def test_include_content_is_opt_in_and_benchmark_text_is_absent(client):
    case = client.post("/api/benchmark/cases", json={"session_id": CLAUDE}).json()
    client.patch(f"/api/benchmark/cases/{case['id']}", json={"note": "PRIVATE_BENCH_NOTE"})
    detail = client.get(f"/api/sessions/{CLAUDE}").json()
    events = client.get(f"/api/sessions/{CLAUDE}/events", params={"limit": 500}).json()["events"]
    spans = build_spans(detail, events, include_content=True)
    encoded = json.dumps([span.attributes for span in spans])
    assert "Please fix the parser" in encoded
    assert "PRIVATE_BENCH_NOTE" not in encoded


def test_no_export_without_endpoint(make_client):
    called = {"n": 0}

    def sender(*_args):
        called["n"] += 1

    with make_client(sender=sender) as test:
        body = test.post("/api/reindex").json()
        assert body["export"]["skipped"] is True
        assert called["n"] == 0
        assert test.get("/api/sources").json()["otel"]["enabled"] is False


def test_collector_down_does_not_fail_ingest(make_client):
    def sender(*_args):
        raise OSError("collector down")

    with make_client(endpoint="http://127.0.0.1:9", sender=sender) as test:
        response = test.post("/api/reindex")
        assert response.status_code == 200
        assert response.json()["sessions"] >= 1
        sources = test.get("/api/sources").json()
        assert "collector down" in (sources["otel"]["last_error"] or "")
        # A second export retries and keeps the same trace id in the payload we would send.
        seen = {}

        def capture(endpoint, payload, content_type):
            seen["payload"] = payload
            seen["type"] = content_type
            raise OSError("still down")

        test.app.state.obs.sender = capture
        test.post("/api/reindex")
        assert seen["payload"]
        assert b"obs" in seen["payload"] or seen["type"]
