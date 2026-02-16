"""
Example: Basic usage of code_fixer library
Demonstrates how to analyze a GitHub issue and generate patches.
"""

import os
from code_fixer import (
    get_github_client,
    fetch_issue,
    build_vector_store,
)
from code_fixer.offline_pipeline import offline_pipeline_issue
from code_fixer.process_layer import LLM


def main():
    # Set up your environment variables first!
    # export GITHUB_TOKEN=your_token
    # export OPENAI_API_KEY=your_key
    
    # Configuration
    REPO_NAME = "owner/repo"
    ISSUE_NUMBER = 123
    PROJECT_PATH = "./projects/repo"
    ISSUES_PATH = "./issues"
    
    # 1. Initialize GitHub client
    print("Initializing GitHub client...")
    github = get_github_client()
    
    # 2. Fetch issue from GitHub
    print(f"Fetching issue #{ISSUE_NUMBER}...")
    issue = fetch_issue(github, REPO_NAME, ISSUE_NUMBER)
    print(f"Issue title: {issue.title}")
    print(f"Issue body: {issue.body[:200]}...")
    
    # 3. Build vector store for context retrieval
    print("\nBuilding vector store...")
    vector_store = build_vector_store(
        codebase_root=PROJECT_PATH,
        issues_jsonl_path=f"{ISSUES_PATH}/issues.jsonl",
        batch_size=500,
        splitter_chunk_size=400
    )
    print("Vector store built successfully!")
    
    # 4. Generate patch suggestions
    print("\nGenerating patch suggestions...")
    result = offline_pipeline_issue(
        prompt="Analyze this issue and propose a fix",
        local_project_path=PROJECT_PATH,
        local_issues_path=ISSUES_PATH,
        issue_number=ISSUE_NUMBER,
        top_k=3
    )
    
    # 5. Display results
    print("\n" + "="*80)
    print("PATCH SUGGESTIONS:")
    print("="*80)
    print(result.content)
    
    # Parse structured output if available
    try:
        from code_fixer.patch_output import PatchSuggestions
        import json
        
        # Assuming the LLM returns JSON
        patch_data = json.loads(result.content)
        patches = PatchSuggestions(**patch_data)
        
        print(f"\nFound {len(patches.edits)} edits:")
        for i, edit in enumerate(patches.edits, 1):
            print(f"\n{i}. {edit.file_path}")
            print(f"   Lines: {edit.line_start_for_editing}-{edit.line_end_for_editing}")
            print(f"   Category: {edit.category}")
            print(f"   Explanation: {edit.explanation_for_edit[:100]}...")
    except Exception as e:
        print(f"\nNote: Could not parse as structured output: {e}")


if __name__ == "__main__":
    main()
