"""Parsing helpers for the content-block format shared by Claude Code and Cursor."""

from __future__ import annotations

from obs.models import Usage
from obs.shared.lineio import int_or_none, stringify


def title_prompt(text: str) -> str | None:
    """Local CLI notices and slash commands are context, not session names."""
    cleaned = text.strip()
    if cleaned.startswith(("<local-command-caveat>", "<local-command-stdout>",
                           "<local-command-stderr>", "<command-name>",
                           "<command-message>")):
        return None
    return " ".join(cleaned.split())[:120] or None


def parse_message_usage(raw) -> Usage | None:
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


def parse_content_blocks(content, typ: str) -> list[dict]:
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
