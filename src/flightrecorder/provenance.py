"""Source identity checks for trusted scripts and imported local Python files."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_identity(path: Path) -> tuple[Path, str | None]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path.resolve().parent), "rev-parse", "--show-toplevel", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        root, commit = result.stdout.splitlines()
        return Path(root), commit
    except (OSError, subprocess.SubprocessError, ValueError):
        return path.resolve().parent, None


def provenance(path: Path) -> dict[str, Any]:
    root, commit = git_identity(path)
    sources = {str(path.resolve().relative_to(root)): digest(path)}
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename or name.startswith("flightrecorder"):
            continue
        source = Path(filename).resolve()
        if source.suffix == ".py" and source.is_relative_to(root) and source.is_file():
            relative = source.relative_to(root)
            if not any(part in {".venv", ".git", "site-packages"} for part in relative.parts):
                sources[str(relative)] = digest(source)
    return {
        "git_commit": commit,
        "source_relative": str(path.resolve().relative_to(root)),
        "source_files": sources,
        "source_scope": "main script + imported local Python files",
    }


def check_source(metadata: dict[str, Any], path: Path) -> None:
    expected, actual = metadata.get("source_sha256"), digest(path)
    root, commit = git_identity(path)
    changed = path.name if expected != actual else None
    for relative, recorded in metadata.get("source_files", {}).items():
        if relative == metadata.get("source_relative"):
            continue
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file() or digest(target) != recorded:
            changed = relative
            break
    if changed:
        raise ValueError(
            f"script source differs from recording: recorded @ SHA {metadata.get('git_commit') or expected}, "
            f"replaying @ SHA {commit or actual}; changed file {changed}; "
            f"recorded source SHA {expected}, current SHA {actual}. Restore the recorded sources."
        )
