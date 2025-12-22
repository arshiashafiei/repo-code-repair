from __future__ import annotations
from typing import Dict, List, Tuple
from .io_utils import http_json_post


def call_model(url: str, payload: Dict, api_key: str | None, temperature: float = 0.0) -> Dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    enriched = {"temperature": temperature, **payload}
    return http_json_post(url, enriched, headers=headers)


def parse_retriever_output(resp: Dict) -> List[str]:
    if not isinstance(resp, dict) or "files for editing" not in resp:
        raise RuntimeError("Retriever output missing 'files for editing'.")
    files = resp["files for editing"]
    if not isinstance(files, list) or not all(isinstance(x, str) for x in files):
        raise RuntimeError("'files for editing' must be a list of paths (strings).")
    return files


def parse_editor_output(resp: Dict) -> Tuple[str, List[Dict[str, str]]]:
    if not isinstance(resp, dict) or "edited code" not in resp:
        raise RuntimeError("Editor output missing 'edited code'.")
    reasoning = resp.get("reasoning process", "")
    edits_raw = resp["edited code"]
    if not isinstance(edits_raw, list):
        raise RuntimeError("'edited code' must be a list.")
    # Each item should have: file, code snippet to be modified, edited code snippet
    for item in edits_raw:
        if not isinstance(item, dict):
            raise RuntimeError("Each edit must be an object.")
        for k in ("file", "code snippet to be modified", "edited code snippet"):
            if k not in item or not isinstance(item[k], str):
                raise RuntimeError("Malformed edit item (file/original/edited).")
    return reasoning, edits_raw
