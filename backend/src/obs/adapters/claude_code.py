from __future__ import annotations

from pathlib import Path
import logging

from obs.adapters.interface import MetadataSnapshot
from obs.models import AgentName, ParsedEvent, ParseResult
from obs.shared.detect import infer_agent_from_path
from obs.shared.discovery import discover_files
from obs.shared.lineio import complete_lines, loads_obj, parse_ts, stringify
from obs.shared.transcripts import parse_content_blocks, parse_message_usage


# Session bookkeeping records are not conversation turns. In particular,
# cost-state is cumulative and must not be counted as per-message usage.
_BOOKKEEPING_TYPES = {
    "mode",
    "permission-mode",
    "atis-latch",
    "file-history-snapshot",
    "last-prompt",
    "cost-state",
    "ai-title",
    "custom-title",
}

log = logging.getLogger(__name__)


class ClaudeCodeAdapter:
    name: AgentName = "claude_code"
    version = 4

    def read_metadata(self, root: Path, user_data_dir: Path | None = None) -> MetadataSnapshot | None:
        titles = self.session_titles(root)
        return None if titles is None else MetadataSnapshot(titles=titles)

    def session_titles(self, root: Path) -> dict[str, str] | None:
        ai_titles: dict[str, str] = {}
        custom_titles: dict[str, str] = {}
        try:
            for path in self.discover(root):
                for line in path.open("rb"):
                    obj, ok = loads_obj(line)
                    if not ok or obj is None:
                        continue
                    typ = obj.get("type")
                    if typ not in {"ai-title", "custom-title"}:
                        continue
                    sid = obj.get("sessionId") or self.native_id_from_path(path)
                    title = obj.get("aiTitle" if typ == "ai-title" else "customTitle")
                    if not isinstance(sid, str) or not isinstance(title, str):
                        continue
                    target = ai_titles if typ == "ai-title" else custom_titles
                    if title.strip():
                        target[sid] = title.strip()
                    else:
                        target.pop(sid, None)
        except OSError:
            log.warning("could not read Claude Code session names from %s", root)
            return None
        return ai_titles | custom_titles

    def detect(self, root: Path) -> bool:
        return infer_agent_from_path(root) == "claude_code"

    def discover(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        base = root / "projects" if (root / "projects").is_dir() else root
        return discover_files(base, "*.jsonl")

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

        if isinstance(typ, str) and typ in _BOOKKEEPING_TYPES:
            return

        if typ == "attachment":
            attachment = obj.get("attachment")
            if isinstance(attachment, dict):
                subtype = attachment.get("type", "attachment")
                rendered = obj.get("rendered")
                texts = (
                    [
                        item["content"]
                        for item in rendered
                        if isinstance(item, dict) and isinstance(item.get("content"), str)
                    ]
                    if isinstance(rendered, list)
                    else []
                )
                text = "\n\n".join(texts) if texts else stringify(attachment)[:2000]
                result.events.append(
                    ParsedEvent(
                        native_id=native,
                        block_index=0,
                        parent_native_id=parent,
                        ts=ts,
                        role="system",
                        kind="system",
                        text=f"Attachment: {subtype}\n{text}",
                        raw_offset=offset,
                        raw_length=length,
                    )
                )
                return

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
                    text=f"Unsupported Claude Code record: {typ!r}",
                    raw_offset=offset,
                    raw_length=length,
                )
            )
            return

        model = message.get("model") if isinstance(message.get("model"), str) else None
        if model:
            models.append(model)
        message_id = message.get("id") if isinstance(message.get("id"), str) else None
        usage = parse_message_usage(message.get("usage"))
        blocks = parse_content_blocks(message.get("content"), typ)
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
