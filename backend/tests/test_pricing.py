from obs.analytics.pricing import Price, Pricing
from obs.models import Usage
import io
import gzip
import json
import pytest
from urllib.error import URLError


def catalog():
    return {"data": [
        {"id": "openai/gpt-6.1-sol", "pricing": {
            "prompt": "0.000002", "completion": "0.00001",
            "input_cache_read": "0.0000001", "input_cache_write": "0.0000025",
            "overrides": [{"min_prompt_tokens": 1000, "prompt": "0.000004"}],
        }},
        {"id": "anthropic/claude-sonnet-5.5", "pricing": {
            "prompt": "0.000002", "completion": "0.00001",
        }},
        {"id": "vendor/free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "vendor/invalid", "pricing": {"prompt": "-1", "completion": "NaN"}},
    ]}


def test_openrouter_cache_refresh_offline_and_retry(tmp_path, monkeypatch):
    calls = []
    now = [100000.0]
    monkeypatch.setattr("obs.analytics.pricing.time.time", lambda: now[0])

    def fetch(url, timeout):
        calls.append(url)
        response = io.BytesIO(json.dumps(catalog()).encode())
        response.headers = {}
        return response

    monkeypatch.setattr("obs.analytics.pricing.urlopen", fetch)
    pricing = Pricing.openrouter(tmp_path)
    pricing.refresh()
    assert len(calls) == 1
    assert pricing.match("gpt-6.1-sol").input == 2
    cached = Pricing.openrouter(tmp_path)
    cached.refresh()
    assert len(calls) == 1
    now[0] += 86401

    def fail(url, timeout):
        calls.append(url)
        raise URLError("offline")

    monkeypatch.setattr("obs.analytics.pricing.urlopen", fail)
    cached.refresh()
    cached.refresh()
    assert len(calls) == 2
    assert cached.match("gpt-6.1-sol").input == 2
    assert Pricing.openrouter(tmp_path).match("gpt-6.1-sol").input == 2
    now[0] += 301
    cached.refresh()
    assert len(calls) == 3


@pytest.mark.parametrize("compressed", [False, True])
def test_openrouter_catalog_response_encoding(tmp_path, monkeypatch, compressed):
    body = json.dumps(catalog()).encode()

    def fetch(request, timeout):
        assert request.full_url == "https://openrouter.ai/api/v1/models"
        assert request.get_header("Accept-encoding") == "gzip"
        assert timeout == 30
        response = io.BytesIO(gzip.compress(body) if compressed else body)
        response.headers = {"Content-Encoding": "gzip"} if compressed else {}
        return response

    monkeypatch.setattr("obs.analytics.pricing.urlopen", fetch)
    pricing = Pricing.openrouter(tmp_path)
    pricing.refresh()
    assert pricing.match("gpt-6.1-sol").input == 2
    assert json.loads(pricing.cache_path.read_text())["catalog"] == catalog()


def test_openrouter_model_mapping_rates_and_tiers(tmp_path):
    import pytest

    pricing = Pricing.openrouter(tmp_path)
    pricing.models = pricing._catalog(catalog())
    assert pricing.match("claude-sonnet-5-5").input == 2
    assert pricing.match("claude-sonnet-5-5-20261001").input == 2
    assert pricing.match("openai/gpt-6.1-sol").input == 2
    assert pricing.match("gpt-6.1-sol-pro") is None
    assert pricing.match("gpt-6.1-sol:batch") is None
    assert pricing.match("vendor/invalid") is None
    assert pricing.estimate("vendor/free", Usage(input_tokens=10)) == 0
    usage = Usage(input_tokens=100, output_tokens=10, cache_read_tokens=80)
    assert pricing.estimate("gpt-6.1-sol", usage, cached_input_included=True) == pytest.approx(0.000148)
    assert pricing.estimate("gpt-6.1-sol", Usage(input_tokens=1000)) == pytest.approx(0.004)


def test_pricing_change_recalculates_unchanged_sessions(client):
    import pytest
    from obs.identity import session_id_for

    state = client.app.state.obs
    session_id = session_id_for("claude_code", "claude-a")
    with state.store.transaction():
        before = state.store.index.execute("SELECT SUM(est_cost_usd) FROM sessions").fetchone()[0]
    state.pricing.models = {
        name: Price(price.input * 2, price.output * 2, price.cache_read * 2, price.cache_write * 2)
        for name, price in state.pricing.models.items()
    }
    result = client.post("/api/reindex").json()
    assert result["files_parsed"] == 0
    with state.store.transaction():
        after = state.store.index.execute("SELECT SUM(est_cost_usd) FROM sessions").fetchone()[0]
    assert after == pytest.approx(before * 2)


def test_longest_prefix_wins_and_unknown_is_none():
    pricing = Pricing(
        {
            "gpt-4o": Price(input=2.5, output=10),
            "gpt-4o-mini": Price(input=0.15, output=0.6),
            "claude-sonnet-4": Price(input=3, output=15),
        }
    )
    assert pricing.match("gpt-4o-mini-2025").input == 0.15
    assert pricing.match("gpt-4o-2024").input == 2.5
    assert pricing.match("claude-sonnet-4-20250514").output == 15
    assert pricing.match("gpt-6.1-sol") is None
    assert pricing.estimate("missing", Usage(input_tokens=10, output_tokens=1)) is None
    assert pricing.estimate("gpt-4o", Usage()) is None
