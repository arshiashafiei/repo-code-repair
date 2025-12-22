# api_client.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import json, time, re
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from prompt import to_chat_messages_payload, generate_retrieval_prompt_from_paths
from retrieval_bm25 import bm25_top_k_files_for_issue
from github_utils import read_issue_title_and_description

import requests

# API_URL = "https://d55ec81d4f5b.ngrok-free.app" + "/retrieve"
API_URL = "https://f4c4f3460918.ngrok-free.app/retrieve"
AUTH_TOKEN = "change-me"

def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    """
    Parse Retry-After header per RFC/MDN: either delta-seconds or HTTP-date.
    Returns seconds to wait, or None if not parseable.
    """
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


def call_swe_fixer_retriever(
    api_url: str,
    auth_token: str,
    messages_payload: Dict[str, Any],
    *,
    timeout: Tuple[float, float] = (9.0, 60.0),  # (connect, read)
    max_retries: int = 3,
) -> List[str]:
    """
    Send the chat 'messages' payload to the swe-fixer-retriever API and return the list of file paths.

    Args:
        api_url: Full endpoint URL of the retriever service.
        auth_token: Bearer token for Authorization.
        messages_payload: Dict as returned by to_chat_messages_payload(...).
        timeout: (connect, read) seconds for the request.
        max_retries: How many times to retry on 429/503 when Retry-After is present.

    Returns:
        A list of file paths (strings) from the model’s output.

    Raises:
        requests.HTTPError on non-OK responses (after retries).
        ValueError if the response doesn’t contain a parseable list of file paths.
    """
    headers = {
        # "Authorization": f"Bearer {auth_token}",   # Bearer token per HTTP auth scheme
        "x-api-key": auth_token ,
        # "Accept": "application/json",
        "Content-Type": "application/json",
    }

    session = requests.Session()
    last_err: Optional[Exception] = None
    print(json.dumps(messages_payload, ensure_ascii=False, indent=2))

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(
                api_url,
                headers=headers,
                json=json.dumps(messages_payload, ensure_ascii=False, indent=2),
                timeout=timeout,
            )
            # Handle rate limiting or maintenance with Retry-After
            if resp.status_code in (429, 503):
                delay = _retry_after_seconds(resp.headers.get("Retry-After"))
                if delay is not None and attempt < max_retries:
                    time.sleep(delay)
                    continue
            resp.raise_for_status()

            data = resp.json()
            print(data)

            # 1) Direct JSON object from the service
            if isinstance(data, dict) and "files for editing" in data:
                files = data["files for editing"]
                if isinstance(files, list) and all(isinstance(x, str) for x in files):
                    return files

            # 2) OpenAI/Chat-style response: choices[0].message.content -> JSON
            if isinstance(data, dict) and "choices" in data and data["choices"]:
                choice = data["choices"][0]
                content = (
                    (choice.get("message") or {}).get("content")
                    or choice.get("text")
                    or ""
                )
                # Try to parse a JSON object/array from the content
                # Prefer an object with {"files for editing": [...]}; fall back to a bare array.
                content_str = content.strip()

                # Find first JSON object/array in the text (tolerate extra prose)
                m = re.search(r"(\{.*\}|\[.*\])", content_str, flags=re.S)
                blob = m.group(1) if m else content_str

                try:
                    parsed = json.loads(blob)
                    if isinstance(parsed, dict) and "files for editing" in parsed:
                        files = parsed["files for editing"]
                        if isinstance(files, list) and all(isinstance(x, str) for x in files):
                            return files
                    if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                        return parsed
                except json.JSONDecodeError:
                    pass  # fall through to error below

            # 3) Some services return the JSON directly in a top-level "output"/"data" key
            for k in ("output", "data", "result"):
                if isinstance(data, dict) and k in data:
                    sub = data[k]
                    if isinstance(sub, dict) and "files for editing" in sub:
                        files = sub["files for editing"]
                        if isinstance(files, list) and all(isinstance(x, str) for x in files):
                            return files

            raise ValueError("Response did not contain a 'files for editing' list.")
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt >= max_retries:
                raise
            # brief backoff on transient network errors
            time.sleep(1.0 * attempt)
        except requests.HTTPError as e:
            # If non-retryable status, raise immediately
            raise
        except Exception as e:
            # Unexpected parsing or runtime issues
            raise

    if last_err:
        raise last_err
    raise RuntimeError("Request failed after retries.")


if __name__ == "__main__":
    issue_text = read_issue_title_and_description(issue_number=8, log=True)
    bm25_retrieved = bm25_top_k_files_for_issue(issue_text=issue_text)
    message = generate_retrieval_prompt_from_paths(file_paths=bm25_retrieved, readme_path="README.md", issue_text=issue_text)
    print("=========================")
    print(message)
    print("=========================")
    call_swe_fixer_retriever(API_URL, AUTH_TOKEN, to_chat_messages_payload(message))
