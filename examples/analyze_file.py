"""
Example: Analyze a single file for code issues
"""

from code_fixer.offline_pipeline import offline_pipeline_file
from code_fixer.patch_output import PatchSuggestions
import json


def analyze_file(file_path, project_path, issues_path):
    """
    Analyze a single file and suggest improvements.
    
    Args:
        file_path: Path to the file to analyze (relative to project_path)
        project_path: Root directory of the project
        issues_path: Directory containing issues data
    """
    
    print(f"Analyzing {file_path}...")
    
    # Generate suggestions using the offline pipeline
    result = offline_pipeline_file(
        prompt="""Analyze this file for:
        - Potential bugs and runtime errors
        - Code smells and maintainability issues
        - Performance concerns
        - Best practice violations
        
        Suggest specific changes with line numbers.""",
        local_project_path=project_path,
        local_issues_path=issues_path,
        local_file_path=file_path,
        top_k=3  # Retrieve top 3 similar contexts
    )
    
    print("\n" + "="*80)
    print(f"ANALYSIS RESULTS FOR: {file_path}")
    print("="*80)
    print(result.content)
    
    return result


def main():
    # Configuration
    PROJECT_PATH = "./projects/my_project"
    ISSUES_PATH = "./issues"
    FILE_TO_ANALYZE = "src/utils/helper.py"
    
    # Analyze the file
    result = analyze_file(
        file_path=FILE_TO_ANALYZE,
        project_path=PROJECT_PATH,
        issues_path=ISSUES_PATH
    )
    
    # Try to extract structured suggestions
    try:
        patch_data = json.loads(result.content)
        patches = PatchSuggestions(**patch_data)
        
        print(f"\n\nSUMMARY:")
        print(f"Total suggestions: {len(patches.edits)}")
        
        # Group by category
        from collections import Counter
        categories = Counter(edit.category for edit in patches.edits)
        print("\nBy category:")
        for category, count in categories.items():
            print(f"  - {category}: {count}")
            
    except Exception as e:
        print(f"\nCould not parse structured output: {e}")


if __name__ == "__main__":
    main()
