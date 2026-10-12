from __future__ import annotations

from pathlib import Path

from obs.adapters.lineio import complete_lines, int_or_none, loads_obj, parse_ts, stringify
from obs.models import ParsedEvent, ParseResult, Usage


class ClaudeCodeAdapter:
    name = "claude_code"
    version = 1

    def detect(self, root: Path) -> bool:
        if not root.exists():
            return False
        if (root / "projects").is_dir():
            return True
        return any(root.glob("*.jsonl"))

    def discover(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        base = root / "projects" if (root / "projects").is_dir() else root
        return sorted(path for path in base.rglob("*.jsonl") if path.is_file())

    def native_id_from_path(self, path: Path) -> str | None:
        if path.parent.name == "subagents":
            return path.stem
        return path.stem or None

    def parent_native_id(self, path: Path) -> str | None:
        if path.parent.name == "subagents":
            return path.parent.parent.name
        return None

    def parse(self, path: Path, start_offset: int) -> ParseResult:
        data = path.read_bytes()
        lines, end_offset = complete_lines(data, start_offset)
        result = ParseResult(
            native_id=self.native_id_from_path(path),
            parent_native_id=self.parent_native_id(path),
            end_offset=end_offset,
        )
        models: list[str] = []
        for offset, length, payload in lines:
            obj, ok = loads_obj(payload)
            if not ok or obj is None:
                text = payload.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                result.events.append(
                    ParsedEvent(
                        native_id=None,
                        block_index=0,
                        parent_native_id=None,
                        ts=None,
                        role="system",
                        kind="unknown",
                        text=text[:2000],
                        raw_offset=offset,
                        raw_length=length,
                    )
                )
                continue
            self._consume(obj, offset, length, result, models)
        result.models = list(dict.fromkeys(models))
        return result

    def _consume(
        self,
        obj: dict,
        offset: int,
        length: int,
        result: ParseResult,
        models: list[str],
    ) -> None:
        session_id = obj.get("sessionId")
        if isinstance(session_id, str) and session_id:
            result.native_id = session_id
        cwd = obj.get("cwd")
        if isinstance(cwd, str) and cwd:
            result.project_cwd = cwd
        branch = obj.get("gitBranch")
        if isinstance(branch, str) and branch:
            result.git_branch = branch
        ts = parse_ts(obj.get("timestamp"))
        if ts is not None:
            if result.started_at is None or ts < result.started_at:
                result.started_at = ts
            if result.ended_at is None or ts > result.ended_at:
                result.ended_at = ts

        typ = obj.get("type")
        native = obj.get("uuid") if isinstance(obj.get("uuid"), str) else None
        parent = obj.get("parentUuid") if isinstance(obj.get("parentUuid"), str) else None

        if typ == "summary":
            summary = obj.get("summary")
            result.events.append(
                ParsedEvent(
                    native_id=native,
                    block_index=0,
                    parent_native_id=parent,
                    ts=ts,
                    role="system",
                    kind="summary",
                    text=summary if isinstance(summary, str) else None,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return

        if typ == "system":
            content = obj.get("content") or obj.get("subtype") or "system"
            text = content if isinstance(content, str) else stringify(content)[:2000]
            result.events.append(
                ParsedEvent(
                    native_id=native,
                    block_index=0,
                    parent_native_id=parent,
                    ts=ts,
                    role="system",
                    kind="system",
                    text=text,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return

        message = obj.get("message") if isinstance(obj.get("message"), dict) else None
        if typ not in ("user", "assistant") or message is None:
            result.events.append(
                ParsedEvent(
                    native_id=native,
                    block_index=0,
                    parent_native_id=parent,
                    ts=ts,
                    role="system",
                    kind="unknown",
                    text=None,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return

        model = message.get("model") if isinstance(message.get("model"), str) else None
        if model:
            models.append(model)
        message_id = message.get("id") if isinstance(message.get("id"), str) else None
        usage = _usage(message.get("usage"))
        blocks = _blocks(message.get("content"), typ)
        for index, block in enumerate(blocks):
            result.events.append(
                ParsedEvent(
                    native_id=native,
                    block_index=index,
                    parent_native_id=parent,
                    ts=ts,
                    role=block["role"],
                    kind=block["kind"],
                    text=block.get("text"),
                    tool_name=block.get("tool_name"),
                    tool_call_id=block.get("tool_call_id"),
                    tool_input=block.get("tool_input"),
                    tool_output=block.get("tool_output"),
                    is_error=bool(block.get("is_error")),
                    model=model,
                    usage=usage if index == 0 else None,
                    usage_origin="message" if index == 0 and usage else None,
                    message_id=message_id,
                    raw_offset=offset,
                    raw_length=length,
                )
            )


def _usage(raw) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    usage = Usage(
        input_tokens=int_or_none(raw.get("input_tokens")),
        output_tokens=int_or_none(raw.get("output_tokens")),
        cache_read_tokens=int_or_none(
            raw.get("cache_read_input_tokens", raw.get("cache_read_tokens"))
        ),
        cache_write_tokens=int_or_none(
            raw.get("cache_creation_input_tokens", raw.get("cache_write_tokens"))
        ),
    )
    return usage if usage.known() else None


def _blocks(content, typ: str) -> list[dict]:
    if isinstance(content, str):
        return [{"role": "user" if typ == "user" else "assistant", "kind": "message", "text": content}]
    if not isinstance(content, list):
        return [{"role": "system", "kind": "unknown", "text": None}]
    blocks: list[dict] = []
    for item in content:
        if isinstance(item, str):
            blocks.append(
                {
                    "role": "user" if typ == "user" else "assistant",
                    "kind": "message",
                    "text": item,
                }
            )
            continue
        if not isinstance(item, dict):
            blocks.append({"role": "system", "kind": "unknown", "text": None})
            continue
        btype = item.get("type")
        if btype == "text":
            blocks.append(
                {
                    "role": "user" if typ == "user" else "assistant",
                    "kind": "message",
                    "text": item.get("text") if isinstance(item.get("text"), str) else "",
                }
            )
        elif btype == "thinking":
            thinking = item.get("thinking")
            if not isinstance(thinking, str):
                thinking = item.get("text") if isinstance(item.get("text"), str) else None
            blocks.append({"role": "assistant", "kind": "thinking", "text": thinking})
        elif btype == "tool_use":
            tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
            blocks.append(
                {
                    "role": "assistant",
                    "kind": "tool_call",
                    "tool_name": item.get("name") if isinstance(item.get("name"), str) else None,
                    "tool_call_id": item.get("id") if isinstance(item.get("id"), str) else None,
                    "tool_input": tool_input,
                }
            )
        elif btype == "tool_result":
            blocks.append(
                {
                    "role": "tool",
                    "kind": "tool_result",
                    "tool_call_id": item.get("tool_use_id")
                    if isinstance(item.get("tool_use_id"), str)
                    else None,
                    "tool_output": stringify(item.get("content")),
                    "is_error": bool(item.get("is_error")),
                }
            )
        else:
            blocks.append(
                {
                    "role": "system",
                    "kind": "unknown",
                    "text": stringify(item)[:2000],
                }
            )
    if not blocks:
        blocks.append({"role": "system", "kind": "unknown", "text": None})
    return blocks
