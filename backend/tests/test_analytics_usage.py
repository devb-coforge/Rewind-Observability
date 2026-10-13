from obs.analytics.queries import timeseries
from obs.db.repo import Store


def test_token_series_keeps_unknown_usage_null(tmp_path):
    store = Store(tmp_path)
    try:
        with store.transaction():
            store.ensure_session({
                "id": "cursor:s1", "agent": "cursor", "native_id": "s1",
                "source_path": "/cursor/s1.jsonl", "project_id": "project",
                "started_at": "2026-10-12T12:00:00.000Z",
            })
            store.index.execute("INSERT INTO session_models VALUES ('cursor:s1', 'model')")
            result = timeseries(store, {}, metric="tokens", bucket="day", group_by="model")
            assert result["points"] == [{"bucket": "2026-10-12", "group": "model", "value": None}]
            store.index.execute("UPDATE sessions SET tokens_in=0, tokens_out=0")
            assert timeseries(store, {}, metric="tokens", bucket="day", group_by="model")["points"][0]["value"] == 0
            store.index.execute("UPDATE sessions SET tokens_in=10, tokens_out=NULL")
            assert timeseries(store, {}, metric="tokens", bucket="day", group_by="model")["points"][0]["value"] == 10
    finally:
        store.close()
