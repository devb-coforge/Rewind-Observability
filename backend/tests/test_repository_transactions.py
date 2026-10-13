import pytest

from obs.db.repo import Store


@pytest.mark.parametrize("fail", [False, True])
def test_feature_repositories_share_nested_transactions(client, fail):
    store = client.app.state.obs.store
    session = client.get("/api/sessions").json()["sessions"][0]
    session_id = session["id"]
    project_id = session["project_id"]

    def write_changes():
        with store.transaction():
            store.set_note(session_id, "Saved note", "2026-10-13T12:00:00.000Z")
            with store.transaction():
                assert store.rename_project(project_id, "Renamed", "2026-10-13T12:00:00.000Z")
                store.set_hidden(project_id, True, "2026-10-13T12:00:00.000Z")
                store.dismiss(project_id, "/other", "2026-10-13T12:00:00.000Z")
            if fail:
                raise RuntimeError("Abort after the nested transaction")

    if fail:
        with pytest.raises(RuntimeError):
            write_changes()
    else:
        write_changes()

    # A separate connection confirms that commits and rollbacks cover both files.
    reopened = Store(store.data_dir)
    try:
        detail = reopened.session_detail(session_id)
        assert detail["project_name"] == (session["project_name"] if fail else "Renamed")
        assert reopened.is_hidden(project_id) is (not fail)
        assert reopened.dismissal_prefixes(project_id) == ([] if fail else ["/other"])
        note = reopened.get_note(session_id)
        if fail:
            assert note is None
        else:
            assert note["text"] == "Saved note"
    finally:
        reopened.close()
