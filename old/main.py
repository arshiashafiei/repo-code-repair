from __future__ import annotations
import argparse
from pathlib import Path
from .config import RunnerConfig
from .io_utils import load_issue_text, load_readme
from .pipeline import run_pipeline
from .git_utils import ensure_git_repo_exist


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Minimal SWE-Fixer-style runner (Python repos)")
    p.add_argument("--repo", required=True, help="Path to repository root")
    p.add_argument("--issue-file", required=True, help="Path to file containing issue text")
    p.add_argument("--test-cmd", default="pytest -q", help="Shell command to run tests (default: pytest -q)")
    p.add_argument("--include", nargs="*", default=["*.py"], help="Glob patterns to include (default: *.py)")
    p.add_argument("--bm25-k", type=int, default=30, help="Number of BM25 candidates (default: 30)")
    p.add_argument("--retriever-url", default=None, help="HTTP URL for retriever model")
    p.add_argument("--editor-url", default=None, help="HTTP URL for editor model")
    p.add_argument("--api-key", default=None, help="Optional Bearer token for both calls")
    p.add_argument("--max-attempts", type=int, default=5, help="Max attempts with resampling (default: 5)")
    p.add_argument("--commit-on-success", action="store_true", help="git add/commit when tests pass")
    p.add_argument("--dry-run", action="store_true", help="Stop after printing retriever input JSON")

    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"[error] repo not found: {repo}")
        return 2

    issue_text = load_issue_text(Path(args.issue_file))
    readme = load_readme(repo)

    cfg = RunnerConfig(
        repo=repo,
        issue_text=issue_text,
        readme=readme,
        include_patterns=args.include,
        bm25_k=args.bm25_k,
        test_cmd=args.test_cmd,
        retriever_url=args.retriever_url,
        editor_url=args.editor_url,
        api_key=args.api_key,
        max_attempts=args.max_attempts,
        dry_run=args.dry_run,
        commit_on_success=args.commit_on_success,
    )

    return run_pipeline(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
