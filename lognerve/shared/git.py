import inspect
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Union

_PACKAGE_DIR = Path(__file__).resolve().parents[1]
_GIT_ROOT: Union[str, bool, None] = None


def read_git_context(git_repo: Optional[str] = None, git_ref: Optional[str] = None) -> Dict[str, Optional[str]]:
    return {
        "git_repo": git_repo or _read_git(["git", "config", "--get", "remote.origin.url"]),
        "git_ref": git_ref or _read_git(["git", "rev-parse", "HEAD"]),
    }


def capture_source_location() -> Dict[str, Any]:
    frame = inspect.currentframe()
    try:
        while frame is not None:
            frame = frame.f_back
            if frame is None:
                break
            filename = Path(frame.f_code.co_filename).resolve()
            if _is_internal_frame(filename):
                continue
            return {"file": _relative_path(str(filename)), "line": frame.f_lineno, "function": frame.f_code.co_name}
    finally:
        del frame
    return {}


def _is_internal_frame(filename: Path) -> bool:
    text = str(filename)
    return text.startswith(str(_PACKAGE_DIR)) or "opentelemetry" in text or "openinference" in text


def _relative_path(filepath: str) -> str:
    git_root = _git_root()
    if git_root and filepath.startswith(git_root):
        return filepath[len(git_root):].lstrip(os.sep)
    cwd = os.getcwd()
    if filepath.startswith(cwd):
        return filepath[len(cwd):].lstrip(os.sep)
    return filepath


def _git_root() -> Optional[str]:
    global _GIT_ROOT
    if _GIT_ROOT is False:
        return None
    if isinstance(_GIT_ROOT, str):
        return _GIT_ROOT
    value = _read_git(["git", "rev-parse", "--show-toplevel"])
    _GIT_ROOT = value if value else False
    return value


def _read_git(command: list) -> Optional[str]:
    try:
        value = subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
        return value or None
    except Exception:
        return None
