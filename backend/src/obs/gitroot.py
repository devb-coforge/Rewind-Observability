"""Locate the git worktree that contains a recorded project directory.

The walk is lexical: it does not call realpath. A `.git` file (linked worktree)
counts the same as a `.git` directory. The nearest marker wins, so a nested
repository stays separate from its parent.
"""

from __future__ import annotations

from pathlib import Path

from obs.identity import normalize_cwd


def git_worktree_root(path: str | None) -> str | None:
    """Return the worktree root containing `path`, or None when no `.git` is found."""
    if not path or not path.startswith("/"):
        return None
    candidate = Path(path)
    while True:
        try:
            found = (candidate / ".git").exists()
        except OSError:
            return None
        if found:
            return normalize_cwd(candidate.as_posix())
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent
