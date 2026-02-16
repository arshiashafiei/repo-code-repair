"""
Summarize GitHub issue discussions using LLM to help with APR (Automated Program Repair).
Reads comments from JSONL, groups by issue, generates summaries, and updates issues JSONL.
"""

import json
import os
from pathlib import Path
from time import sleep
from typing import List, Dict, Any
from collections import defaultdict
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.prompts import PromptTemplate

from . import log
from .process_layer import LLM


DISCUSSION_SUMMARY_PROMPT = """You are analyzing a GitHub issue discussion to help with Automated Program Repair (APR).

Issue Title: {issue_title}
Issue Body: {issue_body}

Discussion Comments:
{comments}

Please provide a concise technical summary that includes:

1. **Bug Description**: What is the specific bug or problem reported?
2. **Symptoms**: How does the bug manifest? (error messages, unexpected behavior, etc.)
3. **Root Cause**: What is causing this issue? (if discussed)
4. **Affected Components**: Which files, functions, or code areas are affected?
5. **Proposed Solutions**: What fixes or workarounds were suggested or discussed?
6. **Resolution Status**: Was the issue resolved? How?

Focus on technical details relevant to code repair. Be specific about code locations, error messages, and implementation details.

Summary:"""


def load_issues(issues_path: str) -> Dict[tuple, Dict[str, Any]]:
    """Load issues from JSONL file, keyed by (repo, issue_number)."""
    issues = {}
    if not Path(issues_path).exists():
        log.log_and_print(f"Issues file not found: {issues_path}")
        return issues
    
    with open(issues_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                issue = json.loads(line)
                key = (issue.get("repo"), issue.get("number"))
                issues[key] = issue
            except json.JSONDecodeError as e:
                log.log_and_print(f"Error parsing issue: {e}")
    
    log.log_and_print(f"Loaded {len(issues)} issues from {issues_path}")
    return issues


def load_comments(comments_path: str) -> Dict[tuple, List[Dict[str, Any]]]:
    """Load comments from JSONL file, grouped by (repo, issue_number)."""
    comments_by_issue = defaultdict(list)
    
    if not Path(comments_path).exists():
        log.log_and_print(f"Comments file not found: {comments_path}")
        return comments_by_issue
    
    with open(comments_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                comment = json.loads(line)
                key = (comment.get("repo"), comment.get("issue_number"))
                comments_by_issue[key].append(comment)
            except json.JSONDecodeError as e:
                log.log_and_print(f"Error parsing comment: {e}")
    
    log.log_and_print(f"Loaded comments for {len(comments_by_issue)} issues from {comments_path}")
    return comments_by_issue


def format_comments(comments: List[Dict[str, Any]]) -> str:
    """Format comments into a readable string for the LLM."""
    if not comments:
        return "No comments."
    
    formatted = []
    for i, comment in enumerate(comments, 1):
        user = comment.get("user", "unknown")
        body = comment.get("body", "").strip()
        created_at = comment.get("created_at", "")
        
        formatted.append(f"Comment {i} by @{user} ({created_at}):\n{body}\n")
    
    return "\n".join(formatted)


def create_summarization_chain():
    prompt = PromptTemplate(
        input_variables=["issue_title", "issue_body", "comments"],
        template=DISCUSSION_SUMMARY_PROMPT,
    )

    chain = prompt | LLM
    return chain


def summarize_issue_discussion(
    issue: Dict[str, Any],
    comments: List[Dict[str, Any]],
    chain
) -> str:
    """Generate summary for a single issue discussion."""
    issue_title = issue.get("title", "No title")
    issue_body = issue.get("body", "No description")
    comments_text = format_comments(comments)
    
    try:
        sleep(1)
        result = chain.invoke({
            "issue_title": issue_title,
            "issue_body": issue_body,
            "comments": comments_text
        })

        return result.content.strip()
    except Exception as e:
        error_info = traceback.format_exc()

        log.log_and_print(f"Error summarizing issue {issue.get('number')}: {error_info}")
        log.log_and_print(f"Error summarizing issue {issue.get('number')}: {e}")
        raise e


def save_issues_with_summaries(issues: Dict[tuple, Dict[str, Any]], output_path: str):
    """Save issues with summaries back to JSONL file."""
    os.makedirs("/".join(output_path.split("/")[:-1]), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for issue_key in sorted(issues.keys()):
            issue = issues[issue_key]
            json.dump(issue, f, ensure_ascii=False)
            f.write("\n")
    
    log.log_and_print(f"Saved {len(issues)} issues with summaries to {output_path}")


def summarize_all_discussions(
    issues_path: str = "issues/issues.jsonl",
    comments_path: str = "comments/comments.jsonl",
    output_path: str | None = None,
    max_workers: int = 3,
):
    """
    Main function to summarize all issue discussions.
    
    Args:
        issues_path: Path to issues JSONL file
        comments_path: Path to comments JSONL file
        output_path: Path to save updated issues (defaults to issues_path)
        max_workers: Number of threads for parallel processing (default: 3)
    """
    if output_path is None:
        output_path = issues_path
    
    log.log_and_print("=" * 60)
    log.log_and_print("Starting issue discussion summarization")
    log.log_and_print("=" * 60)
    
    issues = load_issues(issues_path)
    comments_by_issue = load_comments(comments_path)
    
    if output_path != issues_path and Path(output_path).exists():
        log.log_and_print(f"Loading existing summaries from {output_path}...")
        existing_summaries = load_issues(output_path)
        for key, existing_issue in existing_summaries.items():
            if key in issues and existing_issue.get("discussion_summary"):
                issues[key]["discussion_summary"] = existing_issue["discussion_summary"]
    
    if not issues:
        log.log_and_print("No issues to process. Exiting.")
        return
    
    log.log_and_print("Initializing LLM summarization chain...")
    chain = create_summarization_chain()
    
    issues_with_comments = [k for k in issues.keys() if k in comments_by_issue]
    
    issues_to_process = [
        k for k in issues_with_comments 
        if "discussion_summary" not in issues[k] or not issues[k]["discussion_summary"]
    ]
    already_summarized = len(issues_with_comments) - len(issues_to_process)
    
    log.log_and_print(f"Found {len(issues_with_comments)} issues with comments")
    log.log_and_print(f"Skipping {already_summarized} issues that already have summaries")
    log.log_and_print(f"Processing {len(issues_to_process)} issues with {max_workers} threads...")
    
    write_lock = threading.Lock()
    stats = {"processed": 0, "failed": 0}
    stats_lock = threading.Lock()
    
    def process_single_issue(issue_key):
        """Process a single issue and return the result."""
        repo, issue_num = issue_key
        issue = issues[issue_key]
        comments = comments_by_issue[issue_key]
        
        try:
            log.log_and_print(f"Summarizing {repo} issue #{issue_num}: {issue.get('title', '')[:50]}...")
            
            summary = summarize_issue_discussion(issue, comments, chain)
            
            with write_lock:
                issue["discussion_summary"] = summary
                save_issues_with_summaries(issues, output_path)
            
            log.log_and_print(f"✓ Issue #{issue_num} summarized: {summary[:100]}...")
            
            with stats_lock:
                stats["processed"] += 1
            
            return True
        except Exception as e:
            log.log_and_print(f"⚠ Error summarizing issue #{issue_num}: {e}")
            with stats_lock:
                stats["failed"] += 1
            return False
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_issue, issue_key): issue_key for issue_key in issues_to_process}
        
        for i, future in enumerate(as_completed(futures), 1):
            issue_key = futures[future]
            try:
                future.result()
                log.log_and_print(f"[{i}/{len(issues_to_process)}] Completed issue {issue_key}")
            except Exception as e:
                log.log_and_print(f"[{i}/{len(issues_to_process)}] Failed issue {issue_key}: {e}")
    
    issues_without_comments = [k for k in issues.keys() if k not in comments_by_issue]
    for issue_key in issues_without_comments:
        if "discussion_summary" not in issues[issue_key]:
            issues[issue_key]["discussion_summary"] = "No discussion comments available."
    
    save_issues_with_summaries(issues, output_path)
    
    log.log_and_print("\n" + "=" * 60)
    log.log_and_print("Summarization complete!")
    log.log_and_print(f"Successfully processed: {stats['processed']} issues")
    log.log_and_print(f"Failed: {stats['failed']} issues")
    log.log_and_print(f"Issues without comments: {len(issues_without_comments)}")
    log.log_and_print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Summarize GitHub issue discussions using LLM"
    )
    parser.add_argument(
        "--issues",
        default="issues/issues.jsonl",
        help="Path to issues JSONL file (default: issues/issues.jsonl)",
    )
    parser.add_argument(
        "--comments",
        default="comments/comments.jsonl",
        help="Path to comments JSONL file (default: comments/comments.jsonl)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save updated issues (default: overwrite issues file)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of threads for parallel processing (default: 3)",
    )
    
    args = parser.parse_args()
    
    summarize_all_discussions(
        issues_path=args.issues,
        comments_path=args.comments,
        output_path=args.output,
        max_workers=args.workers,
    )
