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
