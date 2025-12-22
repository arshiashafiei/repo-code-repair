from __future__ import annotations
import subprocess
from pathlib import Path


def ensure_git_repo_exist(repo: Path) -> bool:
    return (repo / ".git").exists()


def git_diff(repo: Path) -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(repo), "diff"], text=True)
    except subprocess.CalledProcessError:
        out = ""
    return out


def git_commit_all(repo: Path, message: str) -> None:
    try:
        subprocess.check_call(["git", "-C", str(repo), "add", "."])
        subprocess.check_call(["git", "-C", str(repo), "commit", "-m", message])
    except subprocess.CalledProcessError:
        pass
