"""
Example: Clone a repository and prepare it for analysis
"""

from code_fixer.github_utils import (
    clone_repo,
    download_codebase,
    fetch_issue,
    fetch_issue_comments,
    get_github_client,
)
import os


def prepare_repository(repo_url: str, commit_hash: str = None):
    """
    Clone a repository and prepare it for code analysis.
    
    Args:
        repo_url: GitHub repository URL
        commit_hash: Optional specific commit to checkout
    """
    
    # Extract repo name from URL
    repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
    target_dir = f"./projects/{repo_name}"
    
    print(f"Preparing repository: {repo_name}")
    print("="*80)
    
    # Clone the repository
    print(f"\n1. Cloning to {target_dir}...")
    clone_repo(
        repo_url=repo_url,
        target_dir=target_dir,
        commit_hash=commit_hash
    )
    print("✓ Repository cloned successfully!")
    
    # Download codebase snapshot
    if commit_hash:
        print(f"\n2. Creating codebase snapshot at commit {commit_hash[:7]}...")
        download_codebase(
            repo_url=repo_url,
            commit_hash=commit_hash,
            output_dir=f"./codebase/{repo_name}"
        )
        print("✓ Codebase snapshot created!")
    
    return target_dir


def fetch_repository_issues(repo_url: str, max_issues: int = 10):
    """
    Fetch recent issues from a repository.
    
    Args:
        repo_url: GitHub repository URL
        max_issues: Maximum number of issues to fetch
    """
    
    # Extract owner/repo from URL
    parts = repo_url.rstrip('/').replace('.git', '').split('/')
    owner, repo = parts[-2], parts[-1]
    repo_full_name = f"{owner}/{repo}"
    
    print(f"\nFetching issues from {repo_full_name}...")
    print("="*80)
    
    # Initialize GitHub client
    github = get_github_client()
    
    # Get repository
    repo_obj = github.get_repo(repo_full_name)
    
    # Fetch open issues
    issues = []
    for i, issue in enumerate(repo_obj.get_issues(state='open'), 1):
        if i > max_issues:
            break
            
        print(f"\nIssue #{issue.number}: {issue.title}")
        print(f"  Created: {issue.created_at}")
        print(f"  Labels: {', '.join(label.name for label in issue.labels)}")
        
        # Fetch comments
        comments = fetch_issue_comments(github, repo_full_name, issue.number)
        print(f"  Comments: {len(comments)}")
        
        issues.append({
            'number': issue.number,
            'title': issue.title,
            'body': issue.body,
            'labels': [label.name for label in issue.labels],
            'comments': comments
        })
    
    print(f"\n✓ Fetched {len(issues)} issues")
    return issues


def main():
    # Example repository
    REPO_URL = "https://github.com/psf/requests"
    COMMIT_HASH = "main"  # or specific commit hash
    
    # Prepare repository
    project_dir = prepare_repository(REPO_URL, COMMIT_HASH)
    
    # Fetch issues
    issues = fetch_repository_issues(REPO_URL, max_issues=5)
    
    print("\n" + "="*80)
    print("SETUP COMPLETE!")
    print("="*80)
    print(f"\nProject directory: {project_dir}")
    print(f"Issues fetched: {len(issues)}")
    print("\nYou can now use other examples to analyze the code!")


if __name__ == "__main__":
    main()
