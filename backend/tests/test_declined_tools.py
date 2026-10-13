import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from obs.config import AppConfig, SourceConfig
from obs.main import create_app
from obs.tool_outcomes import user_declined


@pytest.mark.parametrize('output', [
    'User rejected tool call',
    'Error: exec command rejected by user',
    'aborted by user after 7.7s',
    'aborted by user',
    "The user doesn't want to proceed with this tool use. The tool use was rejected.",
    {'userDecision': 'rejected', 'status': 'cancelled'},
    {'content': [{'type': 'text', 'text': 'tool execution rejected by user'}]},
])
def test_explicit_user_refusals(output):
    assert user_declined(output)


@pytest.mark.parametrize('output', [
    'Permission denied', 'Command exited with code 1',
    'aborted after 7.7s', 'Command cancelled', 'Process aborted by signal',
    {'status': 'cancelled', 'userDecision': 'accepted'},
    {'status': 'rejected', 'reason': 'Automatic approval review rejected the action'},
    {'output': 'User rejected tool call'},
    'Source code contains User rejected tool call',
])
def test_failures_cancellations_and_quoted_output_are_not_user_refusals(output):
    assert not user_declined(output)


def test_cursor_declines_without_output_are_searchable_separately_and_refresh(tmp_path):
    root = tmp_path / 'cursor'
    path = root / 'projects/workspace/agent-transcripts/session/session.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'role': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Shell', 'input': {'command': 'declined command'}},
        {'type': 'tool_use', 'name': 'Shell', 'input': {'command': 'failed command'}},
    ]}}) + '\n')
    base = tmp_path / 'cursor-user'
    dbpath = base / 'globalStorage/state.vscdb'
    dbpath.parent.mkdir(parents=True)
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)')
        for key, command, fields in [
            ('decline', 'declined command', {'userDecision': 'rejected', 'status': 'cancelled'}),
            ('fail', 'failed command', {'status': 'error', 'error': 'Permission denied'}),
            ('cancel', 'cancelled command', {'userDecision': 'accepted', 'status': 'cancelled'}),
            ('orphan', 'unrecorded command', {'userDecision': 'rejected', 'status': 'cancelled'}),
        ]:
            db.execute('INSERT INTO cursorDiskKV VALUES (?, ?)', (
                f'bubbleId:session:{key}', json.dumps({'toolFormerData': {
                    'name': 'run_terminal_command_v2', 'rawArgs': json.dumps({'command': command}), **fields,
                }}),
            ))
    config = AppConfig(sources=[SourceConfig(path=str(root))], cursor_user_data_dir=base,
                       data_dir=tmp_path / 'data', pricing_file=tmp_path / 'missing.yaml', ingest_on_startup=False)
    with TestClient(create_app(config)) as client:
        for full in (False, False, True):
            assert client.post('/api/reindex', params={'full': full}).status_code == 200
            declined = client.get('/api/search/declined', params={'limit': 1}).json()
            assert declined['total'] == 2
            assert len(declined['hits']) == 1
            assert declined['next_offset'] == 1
            second = client.get('/api/search/declined', params={'limit': 1, 'offset': 1}).json()
            assert second['next_offset'] is None
            assert second['hits'][0]['event_id'] != declined['hits'][0]['event_id']
            assert all(json.loads(h['tool_input'])['command'] in ('declined command', 'unrecorded command')
                       for h in declined['hits'] + second['hits'])
            assert client.get('/api/search/declined', params={'q': 'unrecorded'}).json()['hits']
            assert not client.get('/api/search/declined', params={'agent': 'codex'}).json()['hits']
            failures = client.get('/api/search/failures').json()
            assert failures['total'] == 1
            assert 'failed command' in failures['hits'][0]['tool_input']
            assert client.get('/api/sessions/cursor:session').json()['n_tool_errors'] == 1
            events = client.get('/api/sessions/cursor:session/events').json()['events']
            assert sum(e['is_declined'] for e in events) == 2


def test_transcript_decline_is_backfilled_on_adapter_upgrade(tmp_path):
    root = tmp_path / 'claude'
    path = root / 'session.jsonl'
    root.mkdir()
    path.write_text('\n'.join(json.dumps(record) for record in [
        {'type': 'assistant', 'uuid': 'call', 'sessionId': 'session', 'message': {'content': [
            {'type': 'tool_use', 'id': 'c', 'name': 'Bash', 'input': {'command': 'echo declined'}}]}},
        {'type': 'user', 'uuid': 'result', 'sessionId': 'session', 'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': 'c', 'is_error': True,
             'content': "The user doesn't want to proceed with this tool use."}]}},
    ]) + '\n')
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / 'data',
                       pricing_file=tmp_path / 'missing.yaml', ingest_on_startup=False)
    app = create_app(config)
    with TestClient(app) as client:
        client.post('/api/reindex')
        store = app.state.obs.store
        with store.transaction():
            store.index.execute('UPDATE files SET adapter_version = 3')
            store.index.execute('UPDATE events SET is_declined = 0, is_error = 1 WHERE kind = ?', ('tool_result',))
        client.post('/api/reindex')
        assert client.get('/api/search/declined').json()['total'] == 1
        assert client.get('/api/search/failures').json()['total'] == 0


def test_codex_real_approval_cancellation_format_refreshes_existing_index(tmp_path):
    root = tmp_path / 'codex'
    path = root / 'sessions/rollout-2026-10-13T11-37-04-session.jsonl'
    path.parent.mkdir(parents=True)
    command = "printf 'User-decline test: this harmless command was approved.\\n'"
    path.write_text('\n'.join(json.dumps(record) for record in [
        {'timestamp': '2026-10-13T15:55:48.313Z', 'ordinal': 254, 'type': 'response_item', 'payload': {
            'type': 'custom_tool_call', 'id': 'test-call', 'status': 'completed',
            'call_id': 'call-test', 'name': 'exec',
            'input': 'text(await tools.exec_command({cmd:' + json.dumps(command)
                     + ',"sandbox_permissions":"require_escalated"}));\n',
        }},
        {'timestamp': '2026-10-13T15:55:55.984Z', 'ordinal': 256, 'type': 'response_item', 'payload': {
            'type': 'custom_tool_call_output', 'id': 'test-result', 'call_id': 'call-test',
            'output': 'aborted by user after 7.7s',
        }},
    ]) + '\n')
    config = AppConfig(sources=[SourceConfig(path=str(root))], data_dir=tmp_path / 'data',
                       pricing_file=tmp_path / 'missing.yaml', ingest_on_startup=False)
    app = create_app(config)
    with TestClient(app) as client:
        client.post('/api/reindex')
        store = app.state.obs.store
        with store.transaction():
            store.index.execute('UPDATE files SET adapter_version = 4')
            store.index.execute('UPDATE events SET is_declined = 0 WHERE kind = ?', ('tool_result',))
        assert client.get('/api/search/declined').json()['total'] == 0
        assert client.post('/api/reindex').json()['files_parsed'] == 1
        hits = client.get('/api/search/declined').json()['hits']
        assert len(hits) == 1
        assert hits[0]['tool_name'] == 'exec_command'
        assert json.loads(hits[0]['tool_input'])['cmd'] == command
        assert hits[0]['error_preview'] == 'aborted by user after 7.7s'
        assert client.get('/api/search/failures').json()['total'] == 0
