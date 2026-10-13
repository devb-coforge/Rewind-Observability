from pathlib import Path
import json
import pytest

from obs.adapters.codex import CodexAdapter, interpret_tool
from obs.adapters.codex import _output_failed

FIXTURE = (
    Path(__file__).parent / "fixtures" / "codex" / "sessions" / "2026" / "02" / "01" / "rollout-2026-02-01T12-00-00-codex-sess-1.jsonl"
)


def test_codex_maps_messages_tools_and_last_token_usage():
    result = CodexAdapter().parse(FIXTURE, 0)
    assert result.native_id == "codex-sess-1"
    assert result.project_cwd == "/work/proj"
    assert result.git_branch == "feature"
    assert "gpt-4o" in result.models
    calls = [event for event in result.events if event.kind == "tool_call"]
    assert {event.tool_name for event in calls} == {"shell", "exec_command", "apply_patch"}
    shell = next(event for event in calls if event.tool_name == "shell")
    assert shell.tool_input["command"].startswith("ls src")
    paired = [event for event in result.events if event.tool_call_id == "call_1"]
    assert {event.kind for event in paired} == {"tool_call", "tool_result"}
    thinking = next(event for event in result.events if event.kind == "thinking")
    assert "directory" in (thinking.text or "")
    token_events = [event for event in result.events if event.usage_origin == "token_count"]
    assert token_events[0].usage.input_tokens == 30
    assert token_events[0].usage.output_tokens == 12
    record = next(event for event in result.events if event.usage_origin == "token_record")
    assert record.usage.input_tokens == 1000
    assert any(event.kind == "unknown" or (event.kind == "system" and event.text == "agent_message") for event in result.events)


def test_interpret_exec_command_and_apply_patch():
    name, payload = interpret_tool("exec", 'text(await tools.exec_command({cmd:"pwd"}));')
    assert name == "exec_command"
    assert payload["cmd"] == "pwd"
    name, payload = interpret_tool(
        "exec",
        'text(await tools.apply_patch("*** Begin Patch\\n*** Update File: /work/proj/a.py\\n"));',
    )
    assert name == "apply_patch"
    assert "/work/proj/a.py" in payload["patch"]


def test_detects_sessions_root():
    assert CodexAdapter().detect(FIXTURE.parents[4])


def test_session_names_use_latest_valid_entry_and_ignore_partial_lines(tmp_path):
    entries = [
        {"id": "one", "thread_name": "Current name", "updated_at": "2026-10-12T12:00:00Z"},
        {"id": "one", "thread_name": "Old name", "updated_at": "2026-10-12T11:00:00Z"},
        {"id": "two", "thread_name": "Other conversation"},
        {"id": "two", "thread_name": "  "},
        {"id": "three", "thread_name": "  Third conversation  "},
        {"id": "bad", "thread_name": 42},
    ]
    (tmp_path / "session_index.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries) + '\nnot-json\n{"id":'
    )
    assert CodexAdapter().session_titles(tmp_path) == {"one": "Current name", "three": "Third conversation"}


def test_missing_session_index_is_supported(tmp_path):
    assert CodexAdapter().session_titles(tmp_path) == {}


@pytest.mark.parametrize("output,failed", [
    ('Exit code: 1\nOutput:\nfailed', True),
    ('Process exited with code -9\n', True),
    ('Script completed\nOutput:\n{"exit_code":0}\n{"exit_code":7}', True),
    ('{"status":"fulfilled","value":{"exit_code":1}}', True),
    ('{"status":"rejected","reason":"failed"}', True),
    ('{"isError":true,"content":[]}', True),
    ('{"content":[{"type":"text","text":"{\\"exit_code\\":2}"}]}', True),
    ('{"exit_code":null,"session_id":123}', False),
    ('{"exit_code":0,"output":"{\\"exit_code\\":1}"}', False),
    ('{"exit_code":0,"output":"Exit code: 1"}', False),
    ('Example: Exit code: 1', False),
    ('Script failed\nOutput:\n{"exit_code":0}\nScript error:\ninvalid patch', True),
    ('{"exit_code":0,"output":"Script failed\\n"}', False),
])
def test_structured_tool_failure_detection(output, failed):
    assert _output_failed(output) is failed


def test_codex_imports_wrapped_nonzero_exit_code(tmp_path):
    path = tmp_path / "rollout-test.jsonl"
    path.write_text(json.dumps({"type": "response_item", "payload": {
        "type": "custom_tool_call_output", "call_id": "call-1",
        "output": 'Script completed\nOutput:\n{"exit_code":254,"output":"npm failed"}',
    }}) + "\n")
    assert CodexAdapter().parse(path, 0).events[0].is_error


def test_codex_preserves_structured_mcp_error_flag(tmp_path):
    path = tmp_path / "rollout-mcp.jsonl"
    path.write_text(json.dumps({"type": "response_item", "payload": {
        "type": "function_call_output", "call_id": "mcp-1",
        "output": {"isError": True, "content": [{"type": "text", "text": "denied"}]},
    }}) + "\n")
    assert CodexAdapter().parse(path, 0).events[0].is_error
