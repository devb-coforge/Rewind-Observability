from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from obs.adapters.detect import infer_agent_from_path
from obs.adapters.discovery import discover_files
from obs.adapters.lineio import complete_lines, int_or_none, loads_obj, parse_ts, stringify
from obs.models import ParsedEvent, ParseResult, Usage

_TOOL_WRAP = re.compile(r"^text\(await tools\.([A-Za-z0-9_]+)\(", re.DOTALL)
_EXIT_CODE = re.compile(r"^(?:Exit code:|Process exited with code)\s*(-?\d+)\s*$", re.MULTILINE)
log = logging.getLogger(__name__)


class CodexAdapter:
    name = "codex"
    version = 5

    def detect(self, root: Path) -> bool:
        return infer_agent_from_path(root) == "codex"

    def discover(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        base = root / "sessions" if (root / "sessions").is_dir() else root
        return discover_files(base, "rollout-*.jsonl")

    def session_titles(self, root: Path) -> dict[str, str] | None:
        """Read Codex's conversation names without opening its internal state database.

        None means the index could not be read; preserve previously imported names.
        A missing index is normal for transcript-only sources.
        """
        path = root / "session_index.jsonl"
        try:
            lines = path.read_bytes().splitlines()
        except FileNotFoundError:
            return {}
        except OSError:
            log.warning("could not read Codex session names from %s", path)
            return None
        titles: dict[str, str] = {}
        updated: dict[str, datetime | None] = {}
        for line in lines:
            entry, ok = loads_obj(line)
            if not ok or entry is None:
                continue
            sid, name = entry.get("id"), entry.get("thread_name")
            if not isinstance(sid, str) or not sid or not isinstance(name, str):
                continue
            try:
                stamp = parse_ts(entry.get("updated_at"))
            except (ValueError, OverflowError, OSError):
                stamp = None
            previous = updated.get(sid)
            if stamp is not None and previous is not None and stamp < previous:
                continue
            updated[sid] = stamp
            if name.strip():
                titles[sid] = name.strip()
            else:
                titles.pop(sid, None)
        return titles

    def native_id_from_path(self, path: Path) -> str | None:
        stem = path.stem
        if stem.startswith("rollout-"):
            parts = stem.split("-")
            # rollout-YYYY-MM-DDTHH-MM-SS-<uuid>
            if len(parts) >= 2:
                # The uuid uses hyphens, so take everything after the timestamp token.
                # Filename: rollout-2026-10-12T10-15-15-<uuid>
                match = re.search(
                    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
                    stem,
                    re.I,
                )
                if match:
                    return match.group(1)
        return stem or None

    def parent_native_id(self, path: Path) -> str | None:
        return None

    def parse(self, path: Path, start_offset: int) -> ParseResult:
        data = path.read_bytes()
        lines, end_offset = complete_lines(data, start_offset)
        result = ParseResult(native_id=self.native_id_from_path(path), end_offset=end_offset)
        current_model: str | None = None
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
            current_model = self._consume(obj, offset, length, result, current_model, models)
        result.models = list(dict.fromkeys(models))
        return result

    def _consume(
        self,
        obj: dict,
        offset: int,
        length: int,
        result: ParseResult,
        current_model: str | None,
        models: list[str],
    ) -> str | None:
        ts = parse_ts(obj.get("timestamp"))
        if ts is not None:
            if result.started_at is None or ts < result.started_at:
                result.started_at = ts
            if result.ended_at is None or ts > result.ended_at:
                result.ended_at = ts
        typ = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        native = _line_native(obj, payload)
        if native and native.startswith("ord-"):
            # Rollout ordinals restart in every conversation. Event identities
            # must include the session to avoid losing records from other chats.
            native = f"{result.native_id}:{native}"

        if typ == "session_meta":
            sid = payload.get("id") or payload.get("session_id")
            if isinstance(sid, str) and sid:
                result.native_id = sid
            cwd = payload.get("cwd")
            if isinstance(cwd, str) and cwd:
                result.project_cwd = cwd
            branch = _git_branch(payload)
            if branch:
                result.git_branch = branch
            parent = payload.get("parent_session_id")
            if isinstance(parent, str) and parent:
                result.parent_native_id = parent
            started = parse_ts(payload.get("timestamp")) or ts
            if started and (result.started_at is None or started < result.started_at):
                result.started_at = started
            result.events.append(
                _system(native, ts, "session_meta", offset, length, model=current_model)
            )
            return current_model

        if typ == "turn_context":
            model = payload.get("model") if isinstance(payload.get("model"), str) else None
            if model:
                current_model = model
                models.append(model)
            cwd = payload.get("cwd")
            if isinstance(cwd, str) and cwd and not result.project_cwd:
                result.project_cwd = cwd
            result.events.append(
                _system(native, ts, "turn_context", offset, length, model=current_model)
            )
            return current_model

        if typ == "world_state":
            state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
            model = state.get("model") if isinstance(state.get("model"), str) else None
            if model:
                current_model = model
                models.append(model)
            result.events.append(
                _system(native, ts, "world_state", offset, length, model=current_model)
            )
            return current_model

        if typ == "token_usage_record":
            usage = _codex_usage(payload.get("usage"))
            result.events.append(
                _system(
                    native,
                    ts,
                    "token_usage_record",
                    offset,
                    length,
                    model=current_model,
                    usage=usage,
                    usage_origin="token_record" if usage else None,
                )
            )
            return current_model

        if typ == "response_item":
            self._response_item(
                payload, native, ts, offset, length, result, current_model, models
            )
            return current_model

        if typ == "event_msg":
            self._event_msg(payload, native, ts, offset, length, result, current_model, models)
            return current_model

        result.events.append(
            ParsedEvent(
                native_id=native,
                block_index=0,
                parent_native_id=None,
                ts=ts,
                role="system",
                kind="unknown",
                text=typ if isinstance(typ, str) else None,
                model=current_model,
                raw_offset=offset,
                raw_length=length,
            )
        )
        return current_model

    def _response_item(
        self,
        payload: dict,
        native: str | None,
        ts,
        offset: int,
        length: int,
        result: ParseResult,
        current_model: str | None,
        models: list[str],
    ) -> None:
        ptype = payload.get("type")
        item_id = payload.get("id") if isinstance(payload.get("id"), str) else native
        if ptype == "message":
            role = payload.get("role") if isinstance(payload.get("role"), str) else "assistant"
            text = _message_text(payload.get("content"))
            if role == "developer":
                canon_role, kind = "system", "system"
            elif role == "user":
                canon_role, kind = "user", "message"
            else:
                canon_role, kind = "assistant", "message"
            result.events.append(
                ParsedEvent(
                    native_id=item_id,
                    block_index=0,
                    parent_native_id=None,
                    ts=ts,
                    role=canon_role,
                    kind=kind,
                    text=text,
                    model=current_model,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return
        if ptype == "reasoning":
            result.events.append(
                ParsedEvent(
                    native_id=item_id,
                    block_index=0,
                    parent_native_id=None,
                    ts=ts,
                    role="assistant",
                    kind="thinking",
                    text=_reasoning_text(payload.get("summary")),
                    model=current_model,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return
        if ptype in ("function_call", "custom_tool_call"):
            raw_args = payload.get("arguments")
            if not isinstance(raw_args, str):
                raw_args = payload.get("input") if isinstance(payload.get("input"), str) else ""
            declared = payload.get("name") if isinstance(payload.get("name"), str) else "tool"
            tool_name, tool_input = interpret_tool(declared, raw_args)
            call_id = payload.get("call_id") if isinstance(payload.get("call_id"), str) else None
            result.events.append(
                ParsedEvent(
                    native_id=item_id,
                    block_index=0,
                    parent_native_id=None,
                    ts=ts,
                    role="assistant",
                    kind="tool_call",
                    tool_name=tool_name,
                    tool_call_id=call_id,
                    tool_input=tool_input,
                    model=current_model,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return
        if ptype in ("function_call_output", "custom_tool_call_output"):
            output = stringify(payload.get("output"))
            call_id = payload.get("call_id") if isinstance(payload.get("call_id"), str) else None
            is_error = bool(payload.get("is_error")) or _result_failed(payload.get("output")) or _output_failed(output)
            result.events.append(
                ParsedEvent(
                    native_id=item_id,
                    block_index=0,
                    parent_native_id=None,
                    ts=ts,
                    role="tool",
                    kind="tool_result",
                    tool_call_id=call_id,
                    tool_output=output,
                    is_error=is_error,
                    model=current_model,
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return
        result.events.append(
            ParsedEvent(
                native_id=item_id,
                block_index=0,
                parent_native_id=None,
                ts=ts,
                role="system",
                kind="unknown",
                text=ptype if isinstance(ptype, str) else "response_item",
                model=current_model,
                raw_offset=offset,
                raw_length=length,
            )
        )

    def _event_msg(
        self,
        payload: dict,
        native: str | None,
        ts,
        offset: int,
        length: int,
        result: ParseResult,
        current_model: str | None,
        models: list[str],
    ) -> None:
        ptype = payload.get("type") if isinstance(payload.get("type"), str) else "event_msg"
        if ptype == "token_count":
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            last = info.get("last_token_usage")
            usage = _codex_usage(last if isinstance(last, dict) else None)
            result.events.append(
                _system(
                    native,
                    ts,
                    "token_count",
                    offset,
                    length,
                    model=current_model,
                    usage=usage,
                    usage_origin="token_count" if usage else None,
                )
            )
            return
        if ptype == "task_complete":
            completed = parse_ts(payload.get("completed_at")) or ts
            if completed and (result.ended_at is None or completed > result.ended_at):
                result.ended_at = completed
        result.events.append(
            _system(native, ts, ptype, offset, length, model=current_model)
        )


def interpret_tool(declared_name: str, raw: str) -> tuple[str, dict]:
    text = (raw or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return declared_name, parsed
    match = _TOOL_WRAP.match(text)
    if match:
        tool = match.group(1)
        arg = text[match.end() :]
        arg = re.sub(r"\)\s*;?\s*$", "", arg, count=1).strip()
        if tool == "exec_command":
            cmd = _js_field(arg, "cmd")
            return "exec_command", {"cmd": cmd} if cmd is not None else {"raw": text}
        if tool == "apply_patch":
            patch = _js_string_at(arg, 0) if arg[:1] in {"'", '"'} else arg
            return "apply_patch", {"patch": patch if patch is not None else arg}
        return tool, {"raw": text}
    if text:
        return declared_name, {"raw": text}
    return declared_name, {}


def _js_field(arg: str, field: str) -> str | None:
    match = re.search(rf"{field}\s*:\s*", arg)
    if not match:
        return None
    return _js_string_at(arg, match.end())


def _js_string_at(source: str, index: int) -> str | None:
    if index >= len(source) or source[index] not in {"'", '"'}:
        return None
    quote = source[index]
    index += 1
    chars: list[str] = []
    while index < len(source):
        char = source[index]
        if char == "\\":
            if index + 1 >= len(source):
                break
            nxt = source[index + 1]
            chars.append({"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}.get(nxt, nxt))
            index += 2
            continue
        if char == quote:
            return "".join(chars)
        chars.append(char)
        index += 1
    return "".join(chars)


def _codex_usage(raw: dict | None) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    usage = Usage(
        input_tokens=int_or_none(raw.get("input_tokens")),
        output_tokens=int_or_none(raw.get("output_tokens")),
        cache_read_tokens=int_or_none(
            raw.get("cached_input_tokens", raw.get("cache_read_input_tokens"))
        ),
        cache_write_tokens=int_or_none(
            raw.get("cache_write_input_tokens", raw.get("cache_creation_input_tokens"))
        ),
    )
    return usage if usage.known() else None


def _message_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts) if parts else None


def _reasoning_text(summary) -> str | None:
    if isinstance(summary, str):
        return summary or None
    if not isinstance(summary, list):
        return None
    parts: list[str] = []
    for item in summary:
        if isinstance(item, str) and item:
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("summary_text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts) if parts else None


def _output_failed(output: str) -> bool:
    if (output or "").startswith(("Script failed\n", "Script error:", "Error parsing function call:", "Error executing tool")):
        return True
    if any(int(match.group(1)) != 0 for match in _EXIT_CODE.finditer(output or "")):
        return True
    # Exec envelopes contain one JSON result per line, including settled
    # promise values and MCP content blocks. Don't scan command output fields:
    # they may contain source code or transcripts mentioning error flags.
    for line in (output or "").splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if _result_failed(value):
            return True
    return False


def _result_failed(value) -> bool:
    if isinstance(value, list):
        return any(_result_failed(item) for item in value)
    if not isinstance(value, dict):
        return False
    if value.get("is_error") is True or value.get("isError") is True:
        return True
    for key in ("exit_code", "exitCode"):
        code = value.get(key)
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return True
    if value.get("status") == "rejected":
        return True
    if _result_failed(value.get("value")) or _result_failed(value.get("structuredContent")):
        return True
    metadata = value.get("metadata")
    if isinstance(metadata, dict) and _result_failed(metadata):
        return True
    content = value.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                if _output_failed(block.get("text") or ""):
                    return True
    return False


def _git_branch(payload: dict) -> str | None:
    git = payload.get("git")
    if isinstance(git, dict):
        branch = git.get("branch") or git.get("git_branch")
        if isinstance(branch, str) and branch:
            return branch
    branch = payload.get("git_branch")
    if isinstance(branch, str) and branch:
        return branch
    return None


def _line_native(obj: dict, payload: dict) -> str | None:
    for key in ("id", "call_id"):
        if isinstance(payload.get(key), str):
            return payload[key]
    ordinal = obj.get("ordinal")
    if isinstance(ordinal, int):
        return f"ord-{ordinal}"
    return None


def _system(
    native: str | None,
    ts,
    text: str,
    offset: int,
    length: int,
    *,
    model: str | None,
    usage: Usage | None = None,
    usage_origin: str | None = None,
) -> ParsedEvent:
    return ParsedEvent(
        native_id=native,
        block_index=0,
        parent_native_id=None,
        ts=ts,
        role="system",
        kind="system",
        text=text,
        model=model,
        usage=usage,
        usage_origin=usage_origin,
        raw_offset=offset,
        raw_length=length,
    )
