from obs.adapters.claude_code import ClaudeCodeAdapter
from obs.adapters.codex import CodexAdapter
from obs.adapters.cursor import CursorAdapter

ADAPTERS = (ClaudeCodeAdapter(), CodexAdapter(), CursorAdapter())


def adapter_by_name(name: str):
    for adapter in ADAPTERS:
        if adapter.name == name:
            return adapter
    raise KeyError(name)
