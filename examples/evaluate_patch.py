"""
Example: Evaluate patch quality using SWE-Bench metrics
"""

from code_fixer.swe_bench import compute_patch_metrics, apply_patch_suggestions_and_diff


def evaluate_patch(candidate_patch: str, reference_patch: str):
    """
    Evaluate how well a candidate patch matches a reference patch.
    
    Args:
        candidate_patch: The generated patch to evaluate
        reference_patch: The ground truth patch to compare against
    
    Returns:
        dict: Metrics including exact_match, file_match, BLEU scores, etc.
    """
    
    print("Computing patch metrics...")
    print("="*80)
    
    metrics = compute_patch_metrics(
        candidate_patch=candidate_patch,
        reference_patch=reference_patch
    )
    
    # Display results
    print("\nMETRICS:")
    print(f"  Exact Match: {metrics['exact_match']}")
    print(f"  Files Match: {metrics['files_match']}")
    print(f"  File Overlap: {metrics['file_overlap']:.2%}")
    print(f"  Hunk Overlap: {metrics['hunk_overlap']:.2%}")
    print(f"  BLEU-4 (changed lines): {metrics['bleu4_changed_lines']:.4f}")
    print(f"  Edit Distance: {metrics['edit_distance']}")
    print(f"  Add/Remove Lines Match: {metrics['add_remove_lines_match']}")
    
    print("\nCandidate Stats:")
    print(f"  Files: {metrics['candidate_num_files']}")
    print(f"  Hunks: {metrics['candidate_num_hunks']}")
    print(f"  Lines added: {metrics['candidate_lines_added']}")
    print(f"  Lines removed: {metrics['candidate_lines_removed']}")
    
    print("\nReference Stats:")
    print(f"  Files: {metrics['reference_num_files']}")
    print(f"  Hunks: {metrics['reference_num_hunks']}")
    print(f"  Lines added: {metrics['reference_lines_added']}")
    print(f"  Lines removed: {metrics['reference_lines_removed']}")
    
    return metrics


def main():
    # Example patches (simplified)
    reference_patch = """diff --git a/src/utils.py b/src/utils.py
index abc123..def456 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -10,7 +10,7 @@ def calculate(x, y):
-    return x + y
+    return x * y
"""
    
    candidate_patch = """diff --git a/src/utils.py b/src/utils.py
index abc123..def456 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -10,7 +10,7 @@ def calculate(x, y):
-    return x + y
+    return x * y
"""
    
    # Evaluate
    metrics = evaluate_patch(candidate_patch, reference_patch)
    
    # Check if it's a good patch
    if metrics['exact_match']:
        print("\n✓ Perfect match!")
    elif metrics['files_match'] and metrics['hunk_overlap'] > 0.8:
        print("\n✓ Very good match!")
    elif metrics['files_match']:
        print("\n~ Partial match (same files)")
    else:
        print("\n✗ Significant differences")


if __name__ == "__main__":
    main()
