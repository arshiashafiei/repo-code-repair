from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class RunnerConfig:
    repo: Path
    issue_text: str
    readme: str
    include_patterns: List[str]
    bm25_k: int
    test_cmd: str
    retriever_url: Optional[str]
    editor_url: Optional[str]
    api_key: Optional[str]
    max_attempts: int
    dry_run: bool
    commit_on_success: bool
