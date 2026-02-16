from difflib import unified_diff
from typing import List
from patch_output import PatchSuggestions, DiffViewEdits
from io_utils import get_file_content
from log import log_and_print

import re
import subprocess
import tempfile
import os


def validate_patch(patch: str, project_dir: str = None) -> None:
    """
    Basic validation to check if the patch string looks like a unified diff.
    This is a heuristic check and not a full proof validation.
    
    Args:
        patch: The patch string to validate
        project_dir: Optional directory where the git repository is located (e.g., projects/<project_name>)
                     If provided, git apply --check will run in this directory.
    """
    
    if not patch or not isinstance(patch, str):
        raise ValueError(
            "Patch is empty or not a string. "
            "You must provide a non-empty unified diff string."
        )
    
    lines = patch.strip().splitlines()
    if not lines:
        raise ValueError(
            "Patch contains no lines after stripping whitespace. "
            "Ensure the patch is a valid unified diff with content."
        )
    
    # Check for diff header (diff --git or ---)
    has_diff_header = any(
        line.strip().startswith("diff --git") or line.strip().startswith("---") 
        for line in lines[:5]
    )
    if not has_diff_header:
        first_lines = "\n".join(lines[:5])
        raise ValueError(
            f"Missing diff header. The patch must start with 'diff --git a/<path> b/<path>' "
            f"or '--- a/<path>' within the first few lines.\n"
            f"First 5 lines of your patch:\n{first_lines}"
        )
    
    # Check for hunk header (@@ ... @@)
    hunk_pattern = re.compile(r'^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@')
    has_hunk = any(hunk_pattern.match(line.strip()) for line in lines)
    if not has_hunk:
        raise ValueError(
            "Missing hunk header. The patch must contain at least one hunk header "
            "in the format '@@ -<start>,<count> +<start>,<count> @@'. "
            "Ensure the line numbers and counts are correct for the target file."
        )
    
    # Check that there are actual diff lines (starting with +, -, or space)
    diff_line_pattern = re.compile(r'^[ +\-]')
    has_diff_lines = False
    in_hunk = False
    for line in lines:
        if hunk_pattern.match(line.strip()):
            in_hunk = True
            continue
        if in_hunk and diff_line_pattern.match(line.strip()):
            has_diff_lines = True
            break
    
    if not has_diff_lines:
        raise ValueError(
            "No diff content lines found after the hunk header. "
            "Each hunk must contain lines starting with '+' (added), '-' (removed), "
            "or ' ' (context). Ensure your patch includes the actual code changes."
        )
    
    # Validate using git apply --check (only if project_dir is provided)
    if project_dir:
        if not os.path.isdir(project_dir):
            raise FileNotFoundError(
                f"Project directory does not exist: {project_dir}. "
                f"Cannot validate the patch against the target repository."
            )
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as tmp_file:
                tmp_file.write(patch)
                tmp_file.flush()
                tmp_path = tmp_file.name
            
            try:
                # Run git apply --check in the project directory
                result = subprocess.run(
                    ['git', 'apply', '--check', '--verbose', '--recount', '--allow-empty', '--ignore-whitespace', tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=project_dir
                )
                
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    raise RuntimeError(
                        f"git apply --check failed — the patch does not apply cleanly "
                        f"git error output:\n{stderr}\n\n"
                        f"Common causes:\n"
                        f"Regenerate the patch with correct context lines and line numbers matching "
                        f"the current state of the target file."
                    )
                
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except (ValueError, FileNotFoundError, RuntimeError):
            raise
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "git apply --check timed out after 10 seconds. "
                "The patch may be too large or the repository may be in an unusual state."
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during git apply validation: {e}"
            )


def sanitize_patch(raw_patch: str, project_dir: str) -> str:
    """
    Post-process an LLM-generated unified diff to fix common issues:
    1. Remove markdown code fences and trailing non-diff text
    2. Parse diff hunks and locate the intended edits in actual files via fuzzy matching
    3. Apply edits to the real file content
    4. Regenerate a clean, valid unified diff using difflib.unified_diff

    This handles mismatched context lines, wrong hunk counts, and truncated output.
    Returns a corrected patch string, or the cleaned original if processing fails.
    """
    from difflib import unified_diff as _unified_diff

    # Step 1: Clean markdown artifacts
    cleaned = _clean_patch_text(raw_patch)
    if not cleaned.strip():
        log_and_print("[sanitize_patch] Empty after cleaning, returning original")
        return raw_patch

    # Step 2: Parse into per-file hunks
    try:
        file_hunks = _parse_patch_hunks(cleaned)
    except Exception as e:
        log_and_print(f"[sanitize_patch] Parse error: {e}, returning cleaned patch")
        return cleaned

    if not file_hunks:
        log_and_print("[sanitize_patch] No hunks parsed, returning cleaned patch")
        return cleaned

    # Step 3: For each file, locate edits in actual content and regenerate diff
    result_parts = []

    for filepath, hunks in file_hunks.items():
        real_path = os.path.join(project_dir, filepath)
        if not os.path.isfile(real_path):
            log_and_print(f"[sanitize_patch] File not found: {real_path}")
            continue

        try:
            with open(real_path, 'r', errors='replace') as f:
                original_content = f.read()
        except Exception as e:
            log_and_print(f"[sanitize_patch] Cannot read {real_path}: {e}")
            continue

        original_lines_ke = original_content.splitlines(keepends=True)
        if original_lines_ke and not original_lines_ke[-1].endswith('\n'):
            original_lines_ke[-1] += '\n'

        modified_lines = list(original_lines_ke)
        offset = 0
        applied_any = False

        for hunk in sorted(hunks, key=lambda h: h['old_start']):
            old_block = hunk['old_lines']
            new_block = hunk['new_lines']
            removed = hunk['removed_lines']
            added = hunk['added_lines']
            hint = max(0, hunk['old_start'] - 1 + offset)

            if not old_block and not new_block:
                continue

            if not old_block:
                # Pure insertion — place at hint position
                insert_pos = min(hint, len(modified_lines))
                modified_lines[insert_pos:insert_pos] = added
                offset += len(added)
                applied_any = True
                continue

            # Strategy 1: Find full old_block (context + removed lines)
            pos = _find_lines_block(modified_lines, old_block, hint)

            if pos is not None:
                modified_lines[pos:pos + len(old_block)] = new_block
                offset += len(new_block) - len(old_block)
                applied_any = True
                continue

            # Strategy 2: Find only the removed lines (context may be wrong)
            if removed:
                pos = _find_lines_block(modified_lines, removed, hint)
                if pos is not None:
                    modified_lines[pos:pos + len(removed)] = added
                    offset += len(added) - len(removed)
                    applied_any = True
                    continue

            log_and_print(
                f"[sanitize_patch] Could not locate hunk at ~line {hunk['old_start']} "
                f"in {filepath}"
            )

        if not applied_any:
            continue

        # Regenerate a clean diff from actual file content
        original_plain = original_content.splitlines()
        modified_plain = ''.join(modified_lines).splitlines()

        diff = list(_unified_diff(
            original_plain, modified_plain,
            fromfile=f'a/{filepath}', tofile=f'b/{filepath}',
            lineterm='',
        ))

        if diff:
            diff_text = '\n'.join(diff)
            result_parts.append(f'diff --git a/{filepath} b/{filepath}\n{diff_text}')

    if not result_parts:
        log_and_print("[sanitize_patch] No edits applied, returning cleaned patch")
        return cleaned

    result = '\n'.join(result_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result


def _clean_patch_text(text: str) -> str:
    """Remove markdown code fences and trailing non-diff text from LLM output."""
    lines = text.split('\n')
    result = []

    for line in lines:
        if line.strip().startswith('```'):
            continue
        result.append(line)

    # Remove trailing lines that aren't valid diff content
    while result:
        last = result[-1]
        stripped = last.strip()
        if stripped == '':
            result.pop()
            continue
        # Valid diff lines start with specific prefixes
        if stripped.startswith(('diff --git', '--- ', '+++ ', '@@')):
            break
        if last and last[0] in (' ', '-', '+', '\\'):
            break
        # Not a diff line — remove trailing text / explanations
        result.pop()

    return '\n'.join(result)


def _parse_patch_hunks(patch_text: str) -> dict:
    """
    Parse a unified diff into per-file hunks.

    Returns: {filepath: [hunk, ...]}
    Each hunk dict has:
        old_start, old_count, new_start, new_count: int
        old_lines: [str]       - context + removed lines (with newline), in order
        new_lines: [str]       - context + added lines (with newline), in order
        removed_lines: [str]   - only removed lines (with newline)
        added_lines: [str]     - only added lines (with newline)
    """
    hunk_re = re.compile(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@')

    files = {}
    current_file = None
    current_hunk = None

    for raw_line in patch_text.split('\n'):
        # File header
        if raw_line.startswith('diff --git'):
            current_hunk = None
            parts = raw_line.split()
            if len(parts) >= 4:
                path = parts[-1]
                if path.startswith('b/'):
                    path = path[2:]
                current_file = path
            continue

        if raw_line.startswith('--- '):
            continue

        if raw_line.startswith('+++ '):
            if current_file is None and raw_line.startswith('+++ b/'):
                current_file = raw_line[6:]
            continue

        # Hunk header
        m = hunk_re.match(raw_line)
        if m:
            if current_file is None:
                continue
            current_hunk = {
                'old_start': int(m.group(1)),
                'old_count': int(m.group(2)) if m.group(2) else 1,
                'new_start': int(m.group(3)),
                'new_count': int(m.group(4)) if m.group(4) else 1,
                'old_lines': [],
                'new_lines': [],
                'removed_lines': [],
                'added_lines': [],
            }
            files.setdefault(current_file, []).append(current_hunk)
            continue

        # Diff content
        if current_hunk is None:
            continue

        if raw_line.startswith('-'):
            content = raw_line[1:] + '\n'
            current_hunk['old_lines'].append(content)
            current_hunk['removed_lines'].append(content)
        elif raw_line.startswith('+'):
            content = raw_line[1:] + '\n'
            current_hunk['new_lines'].append(content)
            current_hunk['added_lines'].append(content)
        elif raw_line.startswith(' '):
            content = raw_line[1:] + '\n'
            current_hunk['old_lines'].append(content)
            current_hunk['new_lines'].append(content)
        elif raw_line.startswith('\\'):
            continue  # "\ No newline at end of file"
        elif raw_line == '':
            # Possibly an empty context line (LLM may omit the space prefix)
            expected = current_hunk['old_count']
            actual = len(current_hunk['old_lines'])
            if actual < expected:
                current_hunk['old_lines'].append('\n')
                current_hunk['new_lines'].append('\n')

    # Remove empty/incomplete hunks
    for filepath in list(files.keys()):
        files[filepath] = [
            h for h in files[filepath]
            if h['old_lines'] or h['new_lines']
        ]
        if not files[filepath]:
            del files[filepath]

    return files


def _find_lines_block(file_lines, block_lines, hint_start, search_range=150):
    """
    Find block_lines in file_lines, searching outward from hint_start.
    Tries exact match first, then whitespace-normalized match.
    Returns 0-based start index, or None.
    """
    if not block_lines:
        return max(0, min(hint_start, len(file_lines)))

    block_len = len(block_lines)
    max_pos = len(file_lines) - block_len

    if max_pos < 0:
        return None

    hint = max(0, min(hint_start, max_pos))

    def match_exact(pos):
        if pos < 0 or pos > max_pos:
            return False
        return all(
            file_lines[pos + i].rstrip('\n\r') == block_lines[i].rstrip('\n\r')
            for i in range(block_len)
        )

    def match_fuzzy(pos):
        if pos < 0 or pos > max_pos:
            return False
        return all(
            file_lines[pos + i].strip() == block_lines[i].strip()
            for i in range(block_len)
        )

    # Exact match near hint
    for offset in range(min(search_range, max_pos + 1)):
        if match_exact(hint + offset):
            return hint + offset
        if offset > 0 and match_exact(hint - offset):
            return hint - offset

    # Whitespace-normalized match
    for offset in range(min(search_range, max_pos + 1)):
        if match_fuzzy(hint + offset):
            return hint + offset
        if offset > 0 and match_fuzzy(hint - offset):
            return hint - offset

    return None


def apply_patch_and_get_diff(patch: PatchSuggestions, file_path: str) -> str:
    """
    Apply PatchSuggestions to a file and return the git-style unified diff.
    
    Args:
        patch: PatchSuggestions containing edits to apply
        file_path: Path to the file to patch
        
    Returns:
        Git-style unified diff string
        
    Raises:
        ValueError: If snippets don't match, line numbers are invalid, or edits overlap
        FileNotFoundError: If file doesn't exist
    """
    # Read the original file content
    if len(patch.edits) == 0:
        log_and_print("$ NO REPONSE...........")
    original_content = get_file_content(file_path)

    log_and_print(f">>>>>>>> Local file content:\n{original_content}\n<<<<<<<<<<<")
    # Split into lines (keeping line endings for accurate reconstruction)
    original_lines = original_content.splitlines(keepends=True)
    # Ensure last line has newline for consistency
    if original_lines and not original_lines[-1].endswith('\n'):
        original_lines[-1] += '\n'
    
    # Validate and collect edits with their line ranges
    edits_with_ranges: List[tuple] = []  # (start, end, snippet)
    
    for edit in patch.edits:
        # Convert 1-indexed inclusive to 0-indexed (start is 0-indexed, end is exclusive)
        start = edit.line_start_for_editing - 1
        end = edit.line_end_for_editing  # Already exclusive after -1 +1
        
        # Validate line numbers are within bounds
        if start < 0:
            raise ValueError(f"Invalid start line {edit.line_start_for_editing}: must be >= 1")
        if end > len(original_lines):
            raise ValueError(
                f"Invalid end line {edit.line_end_for_editing}: file only has {len(original_lines)} lines"
            )
        if start >= end:
            raise ValueError(
                f"Invalid line range: start ({edit.line_start_for_editing}) must be < end ({edit.line_end_for_editing})"
            )
        
        # Extract the actual content at those lines
        actual_snippet = "".join(original_lines[start:end])
        expected_snippet = edit.exact_existing_buggy_snippet
        
        # Normalize for comparison (handle trailing newline differences)
        actual_normalized = actual_snippet.rstrip('\n')
        expected_normalized = expected_snippet.rstrip('\n')
        
        if actual_normalized != expected_normalized:
            raise ValueError(
                f"Snippet mismatch at lines {edit.line_start_for_editing}-{edit.line_end_for_editing}.\n"
                f"Expected:\n{repr(expected_snippet)}\n"
                f"Actual:\n{repr(actual_snippet)}"
            )
        
        edits_with_ranges.append((start, end, edit))
    
    # Sort by start line to check for overlaps
    edits_with_ranges.sort(key=lambda x: x[0])
    
    # Check for overlapping edits
    for i in range(len(edits_with_ranges) - 1):
        current_start, current_end, current_edit = edits_with_ranges[i]
        next_start, next_end, next_edit = edits_with_ranges[i + 1]
        
        if current_end > next_start:
            raise ValueError(
                f"Overlapping edits detected:\n"
                f"Edit 1: lines {current_edit.line_start_for_editing}-{current_edit.line_end_for_editing}\n"
                f"Edit 2: lines {next_edit.line_start_for_editing}-{next_edit.line_end_for_editing}"
            )
    
    # Apply edits in reverse order (from end of file to beginning)
    # This preserves line numbers for earlier edits
    edits_with_ranges.sort(key=lambda x: x[0], reverse=True)
    
    patched_lines = original_lines.copy()
    
    for start, end, edit in edits_with_ranges:
        replacement = edit.correct_replacement_snippet
        
        # Ensure replacement ends with newline if original block did
        original_block = "".join(original_lines[start:end])
        if original_block.endswith('\n') and not replacement.endswith('\n'):
            replacement += '\n'
        
        # Split replacement into lines
        replacement_lines = replacement.splitlines(keepends=True)
        if replacement_lines and not replacement_lines[-1].endswith('\n'):
            replacement_lines[-1] += '\n'
        
        # Replace the lines
        patched_lines[start:end] = replacement_lines
    
    # Reconstruct patched content
    patched_content = "".join(patched_lines)
    
    # Generate unified diff
    original_for_diff = original_content.splitlines(keepends=True)
    patched_for_diff = patched_content.splitlines(keepends=True)
    
    diff_lines = list(unified_diff(
        original_for_diff,
        patched_for_diff,
        fromfile=f"a/{patch.file_path_to_edit}",
        tofile=f"b/{patch.file_path_to_edit}",
        lineterm=""
    ))
    
    log_and_print(f">>>>>>>> model patch content:\n{patched_for_diff}\n<<<<<<<<<<")
    log_and_print(f"Model suggested path: {patch.file_path_to_edit}")

    # Build git-style diff header
    if not diff_lines:
        diff_output = f"diff --git a/{patch.file_path_to_edit} b/{patch.file_path_to_edit}\n"
    else:
        diff_output = f"diff --git a/{patch.file_path_to_edit} b/{patch.file_path_to_edit}\n"
        diff_output += "\n".join(diff_lines)
        if not diff_output.endswith('\n'):
            diff_output += '\n'
    
    log_and_print(f"#####@@@@@@##### DIFF VIEW #####@@@@@@#####\n{diff_output}")

    return diff_output


def extract_file_documentation(file_content: str) -> dict:
    """
    Extract documentation from a Python file content string.
    
    Args:
        file_content: The content of a Python file as a string.
        
    Returns:
        A dictionary containing:
        - module_docstring: The module-level docstring (if available)
        - classes: List of class info with name, docstring, and method signatures
        - functions: List of function info with name and first/last 5 lines
    """
    import ast
    
    result = {
        "module_docstring": None,
        "classes": [],
        "functions": []
    }
    
    try:
        tree = ast.parse(file_content)
    except SyntaxError:
        return result
    
    lines = file_content.splitlines()
    
    # Extract module docstring
    result["module_docstring"] = ast.get_docstring(tree)
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            # Extract class information
            class_info = {
                "name": node.name,
                "docstring": ast.get_docstring(node),
                "methods": []
            }
            
            # Add base classes to name if present
            if node.bases:
                base_names = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_names.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_names.append(ast.unparse(base))
                    else:
                        base_names.append(ast.unparse(base))
                class_info["name"] = f"{node.name}({', '.join(base_names)})"
            
            # Extract method signatures
            for item in node.body:
                if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                    # Build method signature
                    args = []
                    for arg in item.args.args:
                        arg_str = arg.arg
                        if arg.annotation:
                            arg_str += f": {ast.unparse(arg.annotation)}"
                        args.append(arg_str)
                    
                    # Handle *args
                    if item.args.vararg:
                        args.append(f"*{item.args.vararg.arg}")
                    
                    # Handle **kwargs
                    if item.args.kwarg:
                        args.append(f"**{item.args.kwarg.arg}")
                    
                    signature = f"{item.name}({', '.join(args)})"
                    class_info["methods"].append(signature)
            
            result["classes"].append(class_info)
        
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            # Extract function information
            # Build function signature
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                args.append(arg_str)
            
            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")
            
            func_name = f"{node.name}({', '.join(args)})"
            
            # Get function lines (0-indexed in ast, convert to get actual lines)
            start_line = node.lineno - 1
            end_line = node.end_lineno
            func_lines = lines[start_line:end_line]
            
            # Build content with first 5 and last 5 lines
            if len(func_lines) <= 10:
                content = "\n".join(func_lines)
            else:
                first_five = func_lines[:5]
                last_five = func_lines[-5:]
                content = "\n".join(first_five) + "\n...\n" + "\n".join(last_five)
            
            result["functions"].append({
                "name": func_name,
                "content": content
            })
    
    return result
