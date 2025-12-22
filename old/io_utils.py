from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Optional
from urllib import request


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def load_issue_text(path: Path) -> str:
    return read_text(path)


def load_readme(repo: Path) -> str:
    for name in ["README.md", "README.MD", "README.rst", "README.txt", "README"]:
        p = repo / name
        if p.exists():
            return read_text(p)
    return ""


def http_json_post(url: str, payload: Dict, headers: Optional[Dict[str, str]] = None, timeout: int = 300) -> Dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        text = body.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"Model returned non-JSON response: {text[:500]}")
