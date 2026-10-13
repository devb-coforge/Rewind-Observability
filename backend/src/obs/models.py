from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


AgentName = Literal["claude_code", "codex", "cursor"]
Role = Literal["user", "assistant", "system", "tool"]
Kind = Literal[
    "message",
    "thinking",
    "tool_call",
    "tool_result",
    "system",
    "summary",
    "unknown",
]


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None

    def known(self) -> bool:
        return any(
            value is not None
            for value in (
                self.input_tokens,
                self.output_tokens,
                self.cache_read_tokens,
                self.cache_write_tokens,
            )
        )

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class ParsedEvent:
    native_id: str | None
    block_index: int
    parent_native_id: str | None
    ts: datetime | None
    role: str
    kind: str
    text: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_input: dict | None = None
    tool_output: str | None = None
    is_error: bool = False
    model: str | None = None
    usage: Usage | None = None
    usage_origin: str | None = None
    message_id: str | None = None
    raw_offset: int = 0
    raw_length: int = 0


@dataclass
class ParseResult:
    native_id: str | None = None
    parent_native_id: str | None = None
    project_cwd: str | None = None
    project_key: str | None = None
    project_name: str | None = None
    git_branch: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    models: list[str] = field(default_factory=list)
    events: list[ParsedEvent] = field(default_factory=list)
    end_offset: int = 0
