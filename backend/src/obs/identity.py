"""Lexical paths and stable project ids.

Boundary checks never call realpath and never stat the project tree.
"""

from __future__ import annotations

import base64
import hashlib
import re

FILE_FIELDS = ("file_path", "path", "notebook_path")
SHELL_TOOLS = {
    "bash",
    "shell",
    "exec",
    "exec_command",
    "powershell",
    "cmd",
    "terminal",
}
_PATCH_FILE = re.compile(
    r"^\*\*\* (?:Update File|Add File|Delete File|Move to):[ \t]*(.+)$",
    re.MULTILINE,
)
_ABS_QUOTED = re.compile(r"""["'](/(?:\\.|[^"'])+)["']""")
_ABS_TOKEN = re.compile(r"""(?:^|[\s=])(/(?:[^\s"'`;|&<>])+)|(^/(?:[^\s"'`;|&<>])+)""")


def normalize_cwd(path: str) -> str:
    raw = path.strip().replace("\\", "/")
    if not raw:
        return ""
    absolute = raw.startswith("/")
    out: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if out and out[-1] != "..":
                out.pop()
            elif not absolute:
                out.append("..")
            continue
        out.append(part)
    if absolute:
        return "/" + "/".join(out) if out else "/"
    return "/".join(out)


def lexical_resolve(cwd: str | None, path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    if cleaned.startswith("/"):
        return normalize_cwd(cleaned)
    base = normalize_cwd(cwd or "")
    if not base:
        return normalize_cwd(cleaned)
    if base == "/":
        return normalize_cwd("/" + cleaned)
    return normalize_cwd(base.rstrip("/") + "/" + cleaned)


def is_inside(cwd: str, path: str) -> bool:
    """True when `path` is the cwd or sits under it. Relative paths resolve against cwd."""
    root = normalize_cwd(cwd)
    if root != "/":
        root = root.rstrip("/")
    resolved = lexical_resolve(cwd, path)
    if root == "/":
        return resolved.startswith("/")
    return resolved == root or resolved.startswith(root + "/")


def prefix_match(path: str, prefix: str) -> bool:
    resolved = normalize_cwd(path) if path.startswith("/") else path
    # Callers pass already-resolved absolute paths. Normalize both.
    resolved = normalize_cwd(path)
    pre = normalize_cwd(prefix)
    if not pre:
        return False
    if pre == "/":
        return resolved.startswith("/")
    return resolved == pre or resolved.startswith(pre + "/")


def project_identity(agent: str, cwd: str | None) -> tuple[str, str | None, str | None]:
    """Return (project_id, normalized cwd or None, display name)."""
    if cwd and cwd.strip():
        norm = normalize_cwd(cwd)
        key = f"{agent}\n{norm}"
        name = norm.rstrip("/").split("/")[-1] or norm
    else:
        norm = None
        key = f"{agent}\n"
        name = None
    digest = hashlib.sha256(key.encode()).digest()
    project_id = base64.urlsafe_b64encode(digest[:16]).decode().rstrip("=")
    return project_id, norm, name


def session_id_for(agent: str, native_id: str) -> str:
    return f"{agent}:{native_id}"


def event_id_for(
    agent: str,
    native_id: str | None,
    block_index: int,
    raw_path: str,
    raw_offset: int,
) -> str:
    if native_id:
        return f"{agent}:{native_id}:{block_index}"
    return f"{agent}:{raw_path}:{raw_offset}:{block_index}"


def _strip_trail(path: str) -> str:
    return path.rstrip(").,;:'\"")


def absolute_paths(command: str) -> list[str]:
    found: list[str] = []
    for match in _ABS_QUOTED.finditer(command):
        found.append(_strip_trail(match.group(1).replace("\\ ", " ")))
    for match in _ABS_TOKEN.finditer(command):
        token = match.group(1) or match.group(2)
        if token:
            found.append(_strip_trail(token))
    return _unique(found)


def patch_paths(patch: str) -> list[str]:
    return _unique(match.group(1).strip() for match in _PATCH_FILE.finditer(patch))


def extract_path_refs(tool_name: str | None, tool_input: dict | None) -> list[tuple[str, str]]:
    """Return (path, kind) pairs. kind is 'file' or 'shell'."""
    if not tool_input:
        return []
    name = (tool_name or "").lower()
    refs: list[tuple[str, str]] = []
    patch = tool_input.get("patch")
    if name == "apply_patch" or isinstance(patch, str):
        if isinstance(patch, str):
            refs.extend((item, "file") for item in patch_paths(patch))
    for field in FILE_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str) and value.strip():
            refs.append((value.strip(), "file"))
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            for field in FILE_FIELDS:
                value = edit.get(field)
                if isinstance(value, str) and value.strip():
                    refs.append((value.strip(), "file"))
    if name in SHELL_TOOLS:
        command = None
        for key in ("command", "cmd", "script"):
            if isinstance(tool_input.get(key), str):
                command = tool_input[key]
                break
        if command:
            refs.extend((item, "shell") for item in absolute_paths(command))
    return _unique_pairs(refs)


def classify_paths(
    cwd: str | None,
    refs: list[tuple[str, str]],
) -> list[dict]:
    """Lexical inside/outside classification. No cwd means no alerts."""
    classified: list[dict] = []
    for path, kind in refs:
        if not cwd:
            classified.append(
                {
                    "path": path,
                    "resolved": path,
                    "kind": kind,
                    "outside": False,
                }
            )
            continue
        if kind == "shell":
            resolved = normalize_cwd(path)
            outside = path.startswith("/") and not is_inside(cwd, path)
        else:
            resolved = lexical_resolve(cwd, path)
            outside = not is_inside(cwd, path)
        classified.append(
            {
                "path": path,
                "resolved": resolved,
                "kind": kind,
                "outside": outside,
            }
        )
    return classified


def path_is_allowed(resolved: str, prefixes: list[str]) -> bool:
    return any(prefix_match(resolved, prefix) for prefix in prefixes)


def _unique(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _unique_pairs(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
