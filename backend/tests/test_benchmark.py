CLAUDE = "claude_code:11111111-1111-1111-1111-111111111111"


def test_freeze_survives_reindex_and_summary_groups_by_model(client):
    created = client.post("/api/benchmark/cases", json={"session_id": CLAUDE}).json()
    assert "Please fix the parser" in created["prompt"]
    assert created["model"].startswith("claude-sonnet-4")
    assert created["tokens_in"] == 110
    assert created["est_cost_usd"] is not None
    assert any(item["tool_name"] == "Read" for item in created["tool_summary"])
    assert "print" not in json_dumps(created["tool_summary"])
    client.post("/api/reindex", params={"full": "true"})
    again = client.get(f"/api/benchmark/cases/{created['id']}").json()
    assert again["prompt"] == created["prompt"]
    patched = client.patch(
        f"/api/benchmark/cases/{created['id']}",
        json={"verdict": "pass", "note": "looks right"},
    ).json()
    assert patched["verdict"] == "pass"
    summary = client.get("/api/benchmark/summary").json()
    assert "biased" in summary["note"]
    group = next(item for item in summary["groups"] if item["model"] == created["model"])
    assert group["pass_rate"] == 1
    assert group["n"] == 1
    client.delete(f"/api/benchmark/cases/{created['id']}")
    assert client.get(f"/api/benchmark/cases/{created['id']}").status_code == 404
    remaining = client.get("/api/benchmark/cases").json()["cases"]
    assert remaining == []


def json_dumps(value) -> str:
    import json

    return json.dumps(value)
