import json
from pathlib import Path

from obs.adapters.claude_code import ClaudeCodeAdapter

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "claude"
    / "projects"
    / "-work-proj"
    / "11111111-1111-1111-1111-111111111111.jsonl"
)
SUB = FIXTURE.parent / "11111111-1111-1111-1111-111111111111" / "subagents" / "agent-1.jsonl"


def test_splits_blocks_pairs_calls_and_dedupes_usage():
    result = ClaudeCodeAdapter().parse(FIXTURE, 0)
    kinds = [event.kind for event in result.events]
    assert kinds.count("tool_call") == 2
    assert kinds.count("tool_result") == 2
    assert kinds.count("thinking") == 1
    assert "unknown" in kinds
    assert result.project_cwd == "/work/proj"
    assert result.git_branch == "main"
    calls = {event.tool_call_id: event for event in result.events if event.kind == "tool_call"}
    results = {event.tool_call_id: event for event in result.events if event.kind == "tool_result"}
    assert set(calls) == set(results)
    assert results["toolu_2"].is_error is True
    usages = [event.usage for event in result.events if event.message_id == "msg_1" and event.usage]
    assert len(usages) == 2
    assert usages[0].input_tokens == 100


def test_truncated_last_line_is_not_consumed(tmp_path: Path):
    path = tmp_path / "partial.jsonl"
    path.write_bytes(FIXTURE.read_bytes().splitlines()[0] + b"\n" + b'{"type":"user"')
    result = ClaudeCodeAdapter().parse(path, 0)
    assert len(result.events) == 1
    assert result.end_offset == len(FIXTURE.read_bytes().splitlines()[0]) + 1


def test_subagent_file_points_at_parent():
    adapter = ClaudeCodeAdapter()
    result = adapter.parse(SUB, 0)
    assert result.native_id == "agent-1"
    assert result.parent_native_id == "11111111-1111-1111-1111-111111111111"
    assert adapter.detect(FIXTURE.parents[2])


def test_bookkeeping_and_attachments_are_not_unknown_turns(tmp_path: Path):
    records = [
        {"type": typ, "sessionId": "session-1"}
        for typ in (
            "mode", "permission-mode", "atis-latch", "file-history-snapshot",
            "last-prompt", "cost-state",
        )
    ]
    records += [
        {
            "type": "attachment",
            "uuid": "attachment-1",
            "parentUuid": "user-1",
            "timestamp": "2026-10-12T20:39:17.475Z",
            "cwd": "/work/proj",
            "gitBranch": "main",
            "attachment": {"type": "environment", "snapshot": {}},
            "rendered": [{"content": "Environment reminder"}, {"content": "More context"}],
            "renderedRole": "user",
        },
        {
            "type": "attachment",
            "uuid": "attachment-2",
            "attachment": {"type": "credential_org", "organizationUuid": "org-1"},
        },
        {
            "type": "assistant",
            "message": {
                "content": "Hello!",
                "usage": {"input_tokens": 2, "output_tokens": 72},
            },
        },
    ]
    path = tmp_path / "session-1.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    result = ClaudeCodeAdapter().parse(path, 0)

    assert [event.kind for event in result.events] == ["system", "system", "message"]
    assert result.native_id == "session-1"
    assert result.project_cwd == "/work/proj"
    assert result.git_branch == "main"
    attachment, fallback, message = result.events
    assert attachment.text == "Attachment: environment\nEnvironment reminder\n\nMore context"
    assert attachment.role == "system"
    assert attachment.native_id == "attachment-1"
    assert attachment.parent_native_id == "user-1"
    assert "credential_org" in fallback.text
    assert "org-1" in fallback.text
    assert message.usage.input_tokens == 2
    assert sum(event.usage is not None for event in result.events) == 1
    raw = path.read_bytes()
    assert json.loads(raw[attachment.raw_offset:attachment.raw_offset + attachment.raw_length]) == records[6]
    assert result.end_offset == len(raw)
    assert ClaudeCodeAdapter().parse(path, result.end_offset).events == []


def test_unfamiliar_records_still_have_an_unknown_event(tmp_path: Path):
    path = tmp_path / "unknown.jsonl"
    path.write_text('{"type":"future-record"}\n{"type":"attachment"}\nnot-json\n')
    result = ClaudeCodeAdapter().parse(path, 0)
    assert [event.kind for event in result.events] == ["unknown"] * 3
    assert result.events[0].text == "Unsupported Claude Code record: 'future-record'"
    assert result.events[2].text == "not-json"
