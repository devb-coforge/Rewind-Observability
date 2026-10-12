from obs.adapters.claude_code import ClaudeCodeAdapter
from obs.adapters.codex import CodexAdapter

ADAPTERS = (ClaudeCodeAdapter(), CodexAdapter())


def adapter_by_name(name: str):
    for adapter in ADAPTERS:
        if adapter.name == name:
            return adapter
    raise KeyError(name)
