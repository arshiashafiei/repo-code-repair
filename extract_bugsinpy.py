"""
Extract BugsInPy benchmark data into a JSONL format.

Traverses the BugsInPy repository and extracts:
- Project name and URL
- Bug ID
- Buggy and fixed commit hashes
- Changed file path
- Validity (single file change only)
"""

import json
import os
import re
from pathlib import Path
from typing import Optional


def parse_bug_info(bug_info_path: str) -> dict:
    """
    Parse bug.info file to extract commit hashes.
    
    Expected format:
    buggy_commit_id="abc123..."
    fixed_commit_id="def456..."
    """
    data = {}
    with open(bug_info_path, "r", encoding="utf-8") as f:
        content = f.read()
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or "=" not in line:
                continue
            parts = line.split("=", 1)
            if len(parts) == 2:
                key, value = parts
                # Remove quotes from value
                value = value.strip().strip('"').strip("'")
                data[key.strip()] = value
    
    # Try multiple possible key names
    bug_commit = (data.get("bug_commit_id") or 
                  data.get("bug_commit") or 
                  data.get("buggy_commit_id") or "")
    fix_commit = (data.get("fix_commit_id") or 
                  data.get("fixed_commit_id") or 
                  data.get("fix_commit") or "")
    
    return {
        "bug_commit": bug_commit,
        "fix_commit": fix_commit,
    }


def parse_bug_patch(bug_patch_path: str) -> dict:
    """
    Parse bug_patch.txt to extract file paths and count changed files.
    
    Returns:
    - file_path: The path from the first diff --git line (or None)
    - valid: 1 if only one file changed, 0 if multiple files changed
    - patch_text: The raw patch content
    """
    with open(bug_patch_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Find all "diff --git" lines
    diff_pattern = r"diff --git a/(.*?) b/"
    matches = re.findall(diff_pattern, content)
    
    file_path = matches[0] if matches else None
    valid = 1 if len(matches) == 1 else 0
    
    return {
        "file_path": file_path,
        "valid": valid,
        "num_files_changed": len(matches),
        "patch_text": content,
    }


def parse_project_info(project_info_path: str) -> dict:
    """
    Parse project.info file to extract project URL.
    
    Expected format:
    github_url="https://github.com/..."
    """
    data = {}
    with open(project_info_path, "r", encoding="utf-8") as f:
        content = f.read()
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or "=" not in line:
                continue
            parts = line.split("=", 1)
            if len(parts) == 2:
                key, value = parts
                # Remove quotes from value
                value = value.strip().strip('"').strip("'")
                data[key.strip()] = value
    
    url = (data.get("github_url") or 
           data.get("url") or 
           data.get("repository") or 
           data.get("repo") or "")
    
    return {
        "url": url,
    }


def extract_bugsinpy_data(
    bugsinpy_repo_path: str = "BugsInPy",
    output_file: str = "bugsinpy_bugs.jsonl",
):
    """
    Extract all BugsInPy bug data into a JSONL file.
    
    Args:
        bugsinpy_repo_path: Path to the cloned BugsInPy repository
        output_file: Output JSONL file path
    """
    projects_dir = Path(bugsinpy_repo_path) / "projects"
    
    if not projects_dir.exists():
        raise FileNotFoundError(f"Projects directory not found: {projects_dir}")
    
    records = []
    
    # Iterate through each project
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        
        project_name = project_dir.name
        bugs_dir = project_dir / "bugs"
        project_info_path = project_dir / "project.info"
        
        # Skip if bugs directory doesn't exist
        if not bugs_dir.exists():
            print(f"⚠ No bugs directory for {project_name}")
            continue
        
        # Parse project info
        project_url = ""
        if project_info_path.exists():
            project_info = parse_project_info(str(project_info_path))
            project_url = project_info.get("url", "")
        else:
            print(f"⚠ No project.info for {project_name}")
        
        # Iterate through each bug
        for bug_dir in sorted(bugs_dir.iterdir(), key=lambda x: int(x.name) if x.name.isdigit() else float('inf')):
            if not bug_dir.is_dir():
                continue
            
            bug_id = bug_dir.name
            if not bug_id.isdigit():
                continue
            
            bug_info_path = bug_dir / "bug.info"
            bug_patch_path = bug_dir / "bug_patch.txt"
            
            # Check if required files exist
            if not bug_info_path.exists():
                print(f"⚠ Missing bug.info for {project_name}/{bug_id}")
                continue
            
            if not bug_patch_path.exists():
                print(f"⚠ Missing bug_patch.txt for {project_name}/{bug_id}")
                continue
            
            try:
                # Parse bug info
                bug_info = parse_bug_info(str(bug_info_path))
                
                # Parse bug patch
                patch_info = parse_bug_patch(str(bug_patch_path))
                
                # Create record
                record = {
                    "project": project_name,
                    "url": project_url,
                    "id": int(bug_id),
                    "bug_commit": bug_info["bug_commit"],
                    "fix_commit": bug_info["fix_commit"],
                    "file_path": patch_info["file_path"],
                    "valid": patch_info["valid"],
                    "num_files_changed": patch_info["num_files_changed"],
                    "patch": patch_info["patch_text"],
                }
                
                records.append(record)
                
                status = "✓" if patch_info["valid"] == 1 else "✗"
                print(f"{status} {project_name}/{bug_id}: {patch_info['num_files_changed']} file(s) - {patch_info['file_path']}")
                
            except Exception as e:
                print(f"✗ Error processing {project_name}/{bug_id}: {e}")
                continue
    
    # Write JSONL file
    with open(output_file, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # Print summary
    total_bugs = len(records)
    valid_bugs = sum(1 for r in records if r["valid"] == 1)
    print(f"\n{'='*60}")
    print(f"Total bugs extracted: {total_bugs}")
    print(f"Valid (single file): {valid_bugs}")
    print(f"Invalid (multiple files): {total_bugs - valid_bugs}")
    print(f"Output written to: {output_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract BugsInPy benchmark data into JSONL format"
    )
    parser.add_argument(
        "--repo",
        default="BugsInPy",
        help="Path to BugsInPy repository (default: BugsInPy)",
    )
    parser.add_argument(
        "--output",
        default="bugsinpy_bugs.jsonl",
        help="Output JSONL file (default: bugsinpy_bugs.jsonl)",
    )
    
    args = parser.parse_args()
    
    extract_bugsinpy_data(args.repo, args.output)
