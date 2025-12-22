"""
github_dump.py
- Download repo code into ./codebase/
- Save issues (titles + bodies) to ./issues/issues.jsonl
- Save issue comments to ./comments/comments.jsonl
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from time import sleep
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
from github import Github

try:
    # Newer PyGithub supports typed Auth, but plain token works too.
    from github import Auth  # type: ignore

    _HAS_AUTH = True
except Exception:
    _HAS_AUTH = False

# ---------- helpers ----------


def _parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Accepts:
      - https://github.com/OWNER/REPO
      - https://github.com/OWNER/REPO.git
      - http(s)://github.com/OWNER/REPO/anything...
      - git@github.com:OWNER/REPO.git
    Returns: (owner, repo)
    """
    repo_url = repo_url.strip()

    # git@github.com:owner/repo.git
    m = re.match(
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", repo_url
    )
    if m:
        return m.group("owner"), m.group("repo")

    # https://github.com/owner/repo(.git)?/...
    parsed = urlparse(repo_url)
    if parsed.netloc.lower() != "github.com":
        raise ValueError(f"Not a GitHub URL: {repo_url}")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from URL: {repo_url}")

    owner, repo = parts[0], parts[1]
    repo = re.sub(r"\.git$", "", repo, flags=re.I)
    return owner, repo


def _make_github(token: Optional[str] = None) -> Github:
    token = token or os.getenv("GITHUB_TOKEN")
    if token:
        if _HAS_AUTH:
            return Github(auth=Auth.Token(token))
        return Github(token)  # backwards-compat
    return Github()  # unauthenticated (low rate limit)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_jsonl(path: str, records):
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def _is_pull_request(issue) -> bool:
    # GitHub Issues API includes PRs; detect via 'pull_request' field on issues.
    # PyGithub maps it as an attribute on Issue when present.
    return getattr(issue, "pull_request", None) is not None


# ---------- public functions ----------


def download_codebase(
    repo_url: str,
    out_dir: str = "codebase",
    ref: Optional[str] = None,
    token: Optional[str] = None,
):
    """
    Downloads the repository contents as raw files into `out_dir`, preserving the folder structure.

    Args:
        repo_url: GitHub repo URL (https or git@)
        out_dir: destination directory (default: "codebase")
        ref: branch/tag/commit (default: repo.default_branch)
        token: GitHub token (alternatively set GITHUB_TOKEN env var)
    """
    g = _make_github(token)
    owner, name = _parse_repo_url(repo_url)
    repo = g.get_repo(f"{owner}/{name}")
    if ref is None:
        ref = repo.default_branch

    sleep(1.0)

    archive_url = repo.get_archive_link(archive_format="zipball", ref=ref)

    headers = {}
    tok = token or os.getenv("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"token {tok}"

    resp = requests.get(archive_url, headers=headers, stream=True)
    resp.raise_for_status()

    _ensure_dir(out_dir)

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        for member in z.infolist():
            # Skip top-level folder that GitHub adds, e.g., owner-repo-<sha>/
            rel = member.filename.split("/", 1)
            if len(rel) == 1:
                # it's the top-level directory entry
                continue
            inner_path = rel[1]
            if member.is_dir():
                continue
            dest_path = os.path.join(out_dir, inner_path)
            _ensure_dir(os.path.dirname(dest_path))
            with z.open(member) as src, open(dest_path, "wb") as dst:
                print(f"Copying... {dest_path}")
                shutil.copyfileobj(src, dst)


def save_issues(
    repo_url: str,
    out_dir: str = "issues",
    filename: str = "issues.jsonl",
    token: Optional[str] = None,
    include_prs: bool = False,
):
    """
    Saves repository issues (title + body + metadata) as JSON Lines.

    Args:
        repo_url: GitHub repo URL
        out_dir: output directory (default: "issues")
        filename: output file name (default: "issues.jsonl")
        token: GitHub token or env var
        include_prs: include PRs in addition to issues (default: False)
    """
    g = _make_github(token)
    owner, name = _parse_repo_url(repo_url)
    repo = g.get_repo(f"{owner}/{name}")

    print("====== Adding issues... ======")
    sleep(1.0)

    records = []
    for issue in repo.get_issues(state="all"):  # PyGithub handles pagination
        if not include_prs and _is_pull_request(issue):
            continue

        labels = (
            [lbl.name for lbl in issue.get_labels()]
            if hasattr(issue, "get_labels")
            else []
        )
        assignees = [a.login for a in (issue.assignees or [])]

        print("=========")
        print(f"number: {issue.number}")
        print(f"title: {issue.title}")
        print(f"is_pull_request: {_is_pull_request(issue)}")
        print("==============")

        records.append(
            {
                "repo": f"{owner}/{name}",
                "number": issue.number,
                "title": issue.title or "",
                "body": issue.body or "",
                "state": issue.state,
                "created_at": issue.created_at,
                "updated_at": issue.updated_at,
                "closed_at": issue.closed_at,
                "user": getattr(issue.user, "login", None),
                "assignees": assignees,
                "labels": labels,
                "is_pull_request": _is_pull_request(issue),
                "html_url": issue.html_url,
                "comments_count": issue.comments,
            }
        )

    _write_jsonl(os.path.join(out_dir, filename), records)


def save_issue_comments(
    repo_url: str,
    out_dir: str = "comments",
    filename: str = "comments.jsonl",
    token: Optional[str] = None,
    include_prs: bool = False,
):
    """
    Saves all issue comments (including comments on PR threads as "issue comments")
    as JSON Lines.

    Args:
        repo_url: GitHub repo URL
        out_dir: output directory (default: "comments")
        filename: output file name (default: "comments.jsonl")
        token: GitHub token or env var
        include_prs: include PR issues when iterating (default: False)
    """
    g = _make_github(token)
    owner, name = _parse_repo_url(repo_url)
    repo = g.get_repo(f"{owner}/{name}")

    print("====== Adding issues' comments... ======")
    sleep(1.0)

    records = []
    for issue in repo.get_issues(state="all"):
        if not include_prs and _is_pull_request(issue):
            continue
        for c in issue.get_comments():
            print("===")
            print(f"number: {c.id}")
            print(f"body: {c.body}")
            print("=======")
            records.append(
                {
                    "repo": f"{owner}/{name}",
                    "issue_number": issue.number,
                    "issue_title": issue.title or "",
                    "comment_id": c.id,
                    "user": getattr(c.user, "login", None),
                    "body": c.body or "",
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "html_url": c.html_url,
                }
            )

    _write_jsonl(os.path.join(out_dir, filename), records)


def read_issue_title_and_description(
    issue_number: int,
    issues_path: str = "issues/issues.jsonl",
    log: bool = False,
) -> str:
    """
    Read an issue by its number from a JSON Lines file and return the
    title + description (body) concatenated.

    Args:
        issue_number: The GitHub issue number to find.
        issues_path: Path to the issues JSONL file.
        log: If True, print the concatenated text.

    Returns:
        A single string: "<title>\\n\\n<body>" (body may be empty).

    Raises:
        FileNotFoundError: if issues_path doesn't exist.
        ValueError: if no matching issue is found or a line can't be parsed.
    """
    found: Optional[dict] = None

    with open(issues_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                # Bad line in the JSONL; skip or raise—here we skip.
                continue

            if int(rec.get("number", -1)) == int(issue_number):
                found = rec
                break

    if not found:
        raise ValueError(f"Issue #{issue_number} not found in {issues_path}")

    title = (found.get("title") or "").strip()
    body = (found.get("body") or "").strip()
    combined = f"{title}\n\n{body}" if body else title

    if log:
        print(combined)

    return combined


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Dump GitHub repo code, issues, and comments."
    )
    ap.add_argument("repo_url", help="GitHub repository URL")
    ap.add_argument("--token", help="GitHub token (or set env GITHUB_TOKEN)")
    ap.add_argument(
        "--ref",
        help="Branch/Tag/Commit for code archive (default: repo default branch)",
    )
    ap.add_argument(
        "--include-prs",
        action="store_true",
        help="Include PRs when exporting issues & comments",
    )
    args = ap.parse_args()

    download_codebase(args.repo_url, token=args.token, ref=args.ref)
    save_issues(args.repo_url, token=args.token, include_prs=args.include_prs)
    save_issue_comments(args.repo_url, token=args.token, include_prs=args.include_prs)
    print("Done.")
