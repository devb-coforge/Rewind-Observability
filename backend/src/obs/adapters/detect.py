from __future__ import annotations

from pathlib import Path
from obs.models import AgentName

_CLAUDE_DIR_NAMES = frozenset({".claude", "claude"})
_CODEX_DIR_NAMES = frozenset({".codex", "codex"})
_CURSOR_DIR_NAMES = frozenset({".cursor", "cursor"})


def infer_agent_from_path(path: Path) -> AgentName | None:
    """Map a source root to an agent from its directory name (or explicit config)."""
    name = path.expanduser().name
    if name in _CLAUDE_DIR_NAMES:
        return "claude_code"
    if name in _CODEX_DIR_NAMES:
        return "codex"
    if name in _CURSOR_DIR_NAMES:
        return "cursor"
    return None
