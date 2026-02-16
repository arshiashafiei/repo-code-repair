from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from time import sleep
from typing import Optional, Tuple, Set

from urllib.parse import urlparse
from github import Github, Auth, GithubRetry
from github.Issue import Issue


def _parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Args:
        repo_url: String
        Examples:
            - "https://github.com/OWNER/REPO"
            - "https://github.com/OWNER/REPO.git"
            - "http(s)://github.com/OWNER/REPO/anything..."
            - "git@github.com:OWNER/REPO.git"
    Returns:
        (owner, repo)
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


def _make_github(token: str = "") -> Github:
    if "GITHUB_TOKEN" not in os.environ and not token:
        token = getpass.getpass("Enter your GITHUB_TOKEN: ")

    return Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN", token)),
                  per_page=100,
                  seconds_between_requests=0.25,
                  seconds_between_writes=1.0,
                  retry=GithubRetry(),
        )


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_jsonl(path: str, records, mode: str = "w") -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, mode, encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def _append_jsonl(path: str, record) -> None:
    """Append a single record to a JSONL file (thread-safe with file locking)."""
    _ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read_processed_issue_numbers(issues_path: str) -> Set[int]:
    """Read all issue numbers that have already been processed from a JSONL file."""
    processed = set()
    if not os.path.exists(issues_path):
        return processed
    
    with open(issues_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "number" in rec:
                    processed.add(int(rec["number"]))
            except json.JSONDecodeError:
                continue
    return processed


def _read_processed_comment_ids(comments_path: str) -> Set[int]:
    """Read all comment IDs that have already been processed from a JSONL file."""
    processed = set()
    if not os.path.exists(comments_path):
        return processed
    
    with open(comments_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "comment_id" in rec:
                    processed.add(int(rec["comment_id"]))
            except json.JSONDecodeError:
                continue
    return processed


def _is_pull_request(issue) -> bool:
    return getattr(issue, "pull_request", None) is not None


def _try_git_checkout(out_dir: str, commit_hash: str) -> bool:
    """
    Attempts to checkout the specified commit hash in the given directory.
    
    Args:
        out_dir: Directory that may contain a git repository
        commit_hash: The commit hash to checkout
        
    Returns:
        True if checkout was successful.
        Otherwise, Returns False.
    """
    if not os.path.isdir(out_dir):
        return False
    
    git_dir = os.path.join(out_dir, ".git")
    if not os.path.isdir(git_dir):
        return False
    
    try:
        subprocess.run(
            ["git", "fetch", "--all", "--progress", "--keep"],
            cwd=out_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        
        subprocess.run(
            ["git", "checkout", commit_hash],
            cwd=out_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✓ Successfully checked out to commit {commit_hash[:7]} in existing repo")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Could not checkout {commit_hash[:7]}: {e.stderr.strip() if e.stderr else str(e)}")
        return False
    except Exception as e:
        print(f"Git checkout failed: {e}")
        return False


def _init_git_repo_with_upstream(
    out_dir: str,
    repo_url: str,
    token: str = "",
) -> bool:
    """
    Initializes a git repository in out_dir and sets up the upstream remote.
    
    Args:
        out_dir: Directory to initialize as a git repo
        repo_url: GitHub repo URL to set as upstream (origin)
        token: GitHub token for authenticated access
        
    Returns:
        True if successful, False otherwise
    """
    owner, name = _parse_repo_url(repo_url)
    tok = token or os.getenv("GITHUB_TOKEN")
    
    if tok:
        remote_url = f"https://{tok}@github.com/{owner}/{name}.git"
    else:
        remote_url = f"https://github.com/{owner}/{name}.git"
    
    try:
        subprocess.run(
            ["git", "init"],
            cwd=out_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✓ Initialized git repository in {out_dir}")
        
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=out_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✓ Added origin remote: https://github.com/{owner}/{name}.git")
        
        subprocess.run(
            ["git", "fetch", "--all", "--progress", "--keep"],
            cwd=out_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        print("✓ Fetched all refs from origin")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to initialize git repo: {e.stderr.strip() if e.stderr else str(e)}")
        return False
    except Exception as e:
        print(f"✗ Error initializing git repo: {e}")
        return False

# ---------- public functions ----------

def download_codebase(
    repo_url: str,
    ref: Optional[str] = None,
    token: str = "",
):
    """
    Downloads the repository contents as raw files into `projects/`, preserving the folder structure.

    Args:
        repo_url: GitHub repo URL (https or git@)
        ref: branch/tag/commit (default: repo.default_branch)
        token: GitHub token (alternatively set GITHUB_TOKEN env var)
    """
    g = _make_github(token)
    owner, name = _parse_repo_url(repo_url)
    
    repo = g.get_repo(f"{owner}/{name}")
    if ref is None:
        ref = repo.default_branch
    name = "projects/" + name.lower()
    sleep(1.0)
    if _try_git_checkout(name, ref):
        return True

    tok = token or os.getenv("GITHUB_TOKEN")

    _ensure_dir(name)
    _init_git_repo_with_upstream(name, repo_url, token=tok)
    _try_git_checkout(name, ref)


def get_commit_date_posix(repo_url, commit_hash):
    g = _make_github()
    owner, name = _parse_repo_url(repo_url)
    repo = g.get_repo(f"{owner}/{name}")

    commit = repo.get_commit(commit_hash)
    cutoff_date = commit.commit.author.date.timestamp()
    return str(cutoff_date)


def save_issues_and_comments_before_commit(
    repo_url: str,
    commit_hash: str,
    issues_out_dir: str = "issues",
    issues_filename: str = "issues_before_commit.jsonl",
    comments_out_dir: str = "comments",
    comments_filename: str = "comments_before_commit.jsonl",
    token: str = "",
    include_prs: bool = True,
    max_workers: int = 3,
    time_duration: int = 180,
    save_comments: bool = False,
    only_closed: bool = False
):
    """
    Saves repository issues and comments that were created before a given commit.
    The commit's author date is used as the cutoff time.

    Args:
        repo_url: GitHub repo URL
        commit_hash: Git commit hash to use as the time cutoff
        issues_out_dir: output directory for issues (default: "issues")
        issues_filename: output file name for issues (default: "issues_before_commit.jsonl")
        comments_out_dir: output directory for comments (default: "comments")
        comments_filename: output file name for comments (default: "comments_before_commit.jsonl")
        token: GitHub token or env var
        include_prs: include PRs in addition to issues (default: False)
        max_workers: number of threads for parallel processing (default: 3)
        time_duration: since this time before commit author date [days](180)
        save_comments: save comments or not [False]
        only_closed: to save only closed issues or not [False]
    """

    g = _make_github(token)
    owner, name = _parse_repo_url(repo_url)
    repo = g.get_repo(f"{owner}/{name}")

    _ensure_dir("results")
    print(f"====== Fetching commit {commit_hash[:7]} ======")
    sleep(1.0)
    
    commit = repo.get_commit(commit_hash)
    cutoff_date = commit.commit.author.date
    earliest_date = cutoff_date - timedelta(days=time_duration)
    print(f"Commit date: {cutoff_date}")
    print(f"Earliest date (6 months back): {earliest_date}")
    print(f"Filtering issues and comments created between {earliest_date} and {cutoff_date}...")
    
    issues_filename = issues_filename + str(cutoff_date.timestamp()) + ".jsonl"
    comments_filename = comments_filename + str(cutoff_date.timestamp()) + ".jsonl"
    issues_path = os.path.join(issues_out_dir, issues_filename)
    comments_path = os.path.join(comments_out_dir, comments_filename)
    
    processed_issues = _read_processed_issue_numbers(issues_path)
    processed_comments = _read_processed_comment_ids(comments_path)
    
    if processed_issues:
        print(f"Found {len(processed_issues)} already processed issues, will skip them.")
    if processed_comments:
        print(f"Found {len(processed_comments)} already processed comments, will skip them.")

    print("\n====== Collecting issues before commit... ======")
    sleep(1.0)
    
    issues_lock = threading.Lock()
    comments_lock = threading.Lock()
    stats = {"issues_added": 0, "issues_skipped": 0, "comments_added": 0, "comments_skipped": 0}
    stats_lock = threading.Lock()
    
    def process_issue(issue: Issue):
        """Process a single issue and its comments. Returns counts of processed items."""
        local_stats = {"issues_added": 0, "issues_skipped": 0, "comments_added": 0, "comments_skipped": 0}
        
        if not include_prs and _is_pull_request(issue):
            return local_stats
        
        if only_closed and issue.state == "open":
            return local_stats

        if issue.created_at > cutoff_date:
            return local_stats
        
        if issue.created_at < earliest_date:
            return local_stats
        
        issue_number = issue.number
        
        if issue_number not in processed_issues:
            labels = (
                [lbl.name for lbl in issue.get_labels()]
                if hasattr(issue, "get_labels")
                else []
            )
            assignees = [a.login for a in (issue.assignees or [])]
            
            issue_record = {
                "repo": f"{owner}/{name}",
                "number": issue_number,
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
            
            with issues_lock:
                _append_jsonl(issues_path, issue_record)
                processed_issues.add(issue_number)
    
            print(f"✓ Issue #{issue_number}: {issue.title} (created: {issue.created_at})")
            local_stats["issues_added"] = 1
        else:
            print(f"⏭ Skipping issue #{issue_number} (already processed)")
            local_stats["issues_skipped"] = 1

        if not save_comments:
            return local_stats

        try:
            for c in issue.get_comments():
                if c.created_at > cutoff_date:
                    continue
                    
                comment_id = c.id
                
                if comment_id not in processed_comments:
                    comment_record = {
                        "repo": f"{owner}/{name}",
                        "issue_number": issue_number,
                        "issue_title": issue.title or "",
                        "comment_id": comment_id,
                        "user": getattr(c.user, "login", None),
                        "body": c.body or "",
                        "created_at": c.created_at,
                        "updated_at": c.updated_at,
                        "html_url": c.html_url,
                    }
                    
                    with comments_lock:
                        _append_jsonl(comments_path, comment_record)
                        processed_comments.add(comment_id)  # Update set to avoid duplicates
                    
                    print(f"  ✓ Comment #{comment_id} on issue #{issue_number}")
                    local_stats["comments_added"] += 1
                else:
                    local_stats["comments_skipped"] += 1
        except Exception as e:
            print(f"  ⚠ Error fetching comments for issue #{issue_number}: {e}")
        
        return local_stats
    
    print("Searching for issues within date range using GitHub Search API...")
    
    earliest_str = earliest_date.strftime("%Y-%m-%d")
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")
    
    search_query = f"repo:{owner}/{name} is:issue created:{earliest_str}..{cutoff_str}"
    if include_prs:
        search_query = f"repo:{owner}/{name} created:{earliest_str}..{cutoff_str}"
    
    print(f"Search query: {search_query}")
    search_results = g.search_issues(search_query)
    
    issues_to_process = []
    for issue in search_results:
        if issue.number not in processed_issues:
            issues_to_process.append(issue.number)
    
    print(f"Found {len(issues_to_process)} issues to process (after filtering already processed)\n")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_issue, repo.get_issue(issue_num)): issue_num for issue_num in issues_to_process}
        
        for future in as_completed(futures):
            try:
                local_stats = future.result()
                with stats_lock:
                    for key in stats:
                        stats[key] += local_stats[key]
            except Exception as e:
                issue_id = futures[future]
                print(f"⚠ Error processing issue #{issue_id}: {e}")
    
    print(f"\n" + "=" * 50)
    print(f"✓ Added {stats['issues_added']} new issues (skipped {stats['issues_skipped']} existing)")
    print(f"✓ Added {stats['comments_added']} new comments (skipped {stats['comments_skipped']} existing)")
    print(f"Issues saved to: {issues_path}")
    print(f"Comments saved to: {comments_path}")
    
    return (issues_filename, comments_filename)


# def save_issues(
#     repo_url: str,
#     out_dir: str = "issues",
#     filename: str = "issues.jsonl",
#     token: str = "",
#     include_prs: bool = False,
# ):
#     """
#     Saves repository issues (title + body + metadata) as JSON Lines.

#     Args:
#         repo_url: GitHub repo URL
#         out_dir: output directory (default: "issues")
#         filename: output file name (default: "issues.jsonl")
#         token: GitHub token or env var
#         include_prs: include PRs in addition to issues (default: False)
#     """
#     g = _make_github(token)
#     owner, name = _parse_repo_url(repo_url)
#     repo = g.get_repo(f"{owner}/{name}")

#     print("====== Adding issues... ======")
#     sleep(1.0)

#     records = []
#     for issue in repo.get_issues(state="all"):  # PyGithub handles pagination
#         if not include_prs and _is_pull_request(issue):
#             continue

#         labels = (
#             [lbl.name for lbl in issue.get_labels()]
#             if hasattr(issue, "get_labels")
#             else []
#         )
#         assignees = [a.login for a in (issue.assignees or [])]

#         print("=========")
#         print(f"number: {issue.number}")
#         print(f"title: {issue.title}")
#         print(f"is_pull_request: {_is_pull_request(issue)}")
#         print("==============")

#         records.append(
#             {
#                 "repo": f"{owner}/{name}",
#                 "number": issue.number,
#                 "title": issue.title or "",
#                 "body": issue.body or "",
#                 "state": issue.state,
#                 "created_at": issue.created_at,
#                 "updated_at": issue.updated_at,
#                 "closed_at": issue.closed_at,
#                 "user": getattr(issue.user, "login", None),
#                 "assignees": assignees,
#                 "labels": labels,
#                 "is_pull_request": _is_pull_request(issue),
#                 "html_url": issue.html_url,
#                 "comments_count": issue.comments,
#             }
#         )

#     _write_jsonl(os.path.join(out_dir, filename), records)


# def save_issue_comments(
#     repo_url: str,
#     out_dir: str = "comments",
#     filename: str = "comments.jsonl",
#     token: str = "",
#     include_prs: bool = False,
# ):
#     """
#     Saves all issue comments (including comments on PR threads as "issue comments")
#     as JSON Lines.

#     Args:
#         repo_url: GitHub repo URL
#         out_dir: output directory (default: "comments")
#         filename: output file name (default: "comments.jsonl")
#         token: GitHub token or env var
#         include_prs: include PR issues when iterating (default: False)
#     """
#     g = _make_github(token)
#     owner, name = _parse_repo_url(repo_url)
#     repo = g.get_repo(f"{owner}/{name}")

#     print("====== Adding issues' comments... ======")
#     sleep(1.0)

#     records = []
#     for issue in repo.get_issues(state="all"):
#         if not include_prs and _is_pull_request(issue):
#             continue
#         for c in issue.get_comments():
#             print("===")
#             print(f"number: {c.id}")
#             print(f"body: {c.body}")
#             print("=======")
#             records.append(
#                 {
#                     "repo": f"{owner}/{name}",
#                     "issue_number": issue.number,
#                     "issue_title": issue.title or "",
#                     "comment_id": c.id,
#                     "user": getattr(c.user, "login", None),
#                     "body": c.body or "",
#                     "created_at": c.created_at,
#                     "updated_at": c.updated_at,
#                     "html_url": c.html_url,
#                 }
#             )

#     _write_jsonl(os.path.join(out_dir, filename), records)


# if __name__ == "__main__":
#     import argparse

#     ap = argparse.ArgumentParser(
#         description="Dump GitHub repo code, issues, and comments."
#     )
#     ap.add_argument("repo_url", help="GitHub repository URL")
#     ap.add_argument("--token", help="GitHub token (or set env GITHUB_TOKEN)")
#     ap.add_argument(
#         "--ref",
#         help="Branch/Tag/Commit for code archive (default: repo default branch)",
#     )
#     ap.add_argument(
#         "--include-prs",
#         action="store_true",
#         help="Include PRs when exporting issues & comments",
#     )
#     args = ap.parse_args()

#     download_codebase(args.repo_url, token=args.token, ref=args.ref)
#     save_issues(args.repo_url, token=args.token, include_prs=args.include_prs)
#     save_issue_comments(args.repo_url, token=args.token, include_prs=args.include_prs)
#     print("Done.")
