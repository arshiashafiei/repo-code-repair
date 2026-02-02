from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple
from pathlib import Path
import jsonlines


TEXT_EXTS = {
    ".py", ".md", ".txt", ".rst", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg",
    ".dockerfile", ".env", ".sh", ".bat",
}


def get_file_content(path: str) -> str:
    """
    Returns [str] file text content from [str] a path.
    Accepts both absolute paths and relative paths (which will be prefixed with 'codebase/').
    """
    try:
        p = Path(path)
        if not p.is_absolute() and not p.exists():
            p = Path("codebase") / path
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    except OSError:
        return ""


def iter_text_files(codebase_root: str) -> Iterable[Path]:
    root = Path(codebase_root)
    for p in root.rglob("*"):
        if p.is_dir():
            continue

        if any(part in {".git", "__pycache__", ".venv", "venv", "node_modules"} for part in p.parts):
            continue
        if p.suffix.lower() in TEXT_EXTS or p.name.lower() in {"dockerfile"}:
            yield p


def iter_issues_jsonl() -> Iterable[Any]:
    with jsonlines.open("issues/issues.jsonl") as reader:
        for issue in reader:
            yield issue


def get_issue_content(issue_number: int, issues_path_jsonl: str = "issues/issues.jsonl") -> tuple[str | None, str | None, str | None]:
    """
    Returns tuple[str | None, str | None, str | None] issue text content from [int] an id:
    (issue["title"], issue["body"], issue["labels"]) 
    """
    with jsonlines.open(issues_path_jsonl) as reader:
        for issue in reader:
            if issue["number"] == issue_number:
                return (issue["title"], issue["body"], issue["labels"])
                
    return (None, None, None)


def get_issues_comments_content(issue_number: int) -> list[tuple[str, str]]:
    """
    Returns list[tuple[str, str]] comments under and issue for [int] an issue number:
    (comment["commment_id"], comment["body"]) 
    """
    comments: list[tuple[str, str]] = []
    with jsonlines.open("commments.jsonl") as reader:
        for comment in reader:
            if comment["issue_number"] == issue_number:
                comments.append((comment["commment_id"], comment["body"]))
                
    return comments
