SYSTEM_PROMPT_PYTHON_PROGRAMMER = """You are an expert python programmer. Your task is to review and solve github issues based on repository context."""

SYSTEM_PROMPT_EMPTY = ""


OUTPUT_FORMAT = """
OUTPUT FORMAT:
Output ONLY a single JSON object that conforms to this schema:
  PatchSuggestions = {
    "file_path_to_edit": string,
    "edits": [
      {
        "category": "SYNTAX_ERROR" | "LINTING" | "OTHER",
        "confidence": number,
        "evidence": string,
        "line_start_for_editing": integer,
        "line_end_for_editing": integer,
        "exact_existing_buggy_snippet": string,
        "correct_replacement_snippet": string
      }, ...
    ]
  }
- No extra keys. No surrounding text. No markdown. No code fences.
- All strings must be valid JSON strings (escape newlines as \n and quotes as \").
"""

OUTPUT_FORMAT_Diffview = """
OUTPUT FORMAT:
Output ONLY a single JSON object that conforms to this schema:
  DiffViewEdits = {
    "patch": string
  }
- No extra keys. No surrounding text. No markdown. No code fences. No explanations.
- All strings must be valid JSON strings (escape newlines as \\n and quotes as \\").
- The "patch" value MUST be a valid unified diff for `git apply`.

CRITICAL RULES for generating the unified diff:
1. Start each file with `diff --git a/<path> b/<path>`.
2. Include `--- a/<path>` and `+++ b/<path>` lines.
3. Use hunk headers: `@@ -<old_start>,<old_count> +<new_start>,<new_count> @@`
   - old_count = total lines from old file in this hunk (context + removed lines)
   - new_count = total lines in new version of this hunk (context + added lines)
4. Context lines (unchanged) MUST start with a single space ' ' and be copied
   EXACTLY character-for-character from the provided file content, preserving
   all indentation, whitespace, and punctuation. Never alter context lines.
5. Removed lines start with '-' followed by the EXACT original line content.
6. Added lines start with '+' followed by the new content.
7. Include 3 lines of unchanged context before and after each change.
8. Every hunk MUST be complete — never truncate or leave partial lines.
9. Use correct line numbers matching the provided file content.
10. Do NOT include any trailing text, markdown fences, or explanations after the diff.

Example (single hunk, 3 context lines before and after):
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -10,7 +10,7 @@
     results = []
     for item in data:
         if item is not None:
-            results.append(str(item))
+            results.append(item.strip())
         else:
             results.append("")
     return results
"""


OUTPUT_FORMAT_FILESTOEDIT = """
OUTPUT FORMAT:
Output ONLY a single JSON object that conforms to this schema:
  FilesToEdit = {
    "files_for_editing": [
      "file_path_1",
      "file_path_2",
      "file_path_3"
    ],
  }
- No extra keys. No surrounding text. No markdown. No code fences.
- All strings must be valid JSON strings (escape newlines as \n and quotes as \").
- return ONLY 3 items in files_for_editing
"""

USER_PROMPT_FILESTOEDIT = """
Given the issue statement and its top 30 similar files in code base as file skeletons,
your task is to select ONLY 3 files you think that are most related to the issue and need to be edited in order to solve the issue.
you should ONLY select from the top 30 files given to you.
The file skeletons includes the module
docstring (if available). It also contains class names,
their associated docstrings, and all method names. For
functions, only the name and the first/last five lines of
code are included.
"""

USER_PROMPT_V6 = """
Given the file content and it's related context below,
produce a list of edit suggestions that fix the reported problems with the smallest safe changes.
"""

USER_PROMPT_ZERO_SHOT_ISSUES = """
Given the issue statement and it's related context below,
produce a list of edit suggestions that fixes the issue with the smallest safe changes.
"""

USER_PROMPT_COT_ISSUES = """
You will be provided with a github issue statement and its related context below, explaining a problem to resolve.
Follow the steps below to solve the issue
step 1: read the given issue statement and its related context
step 2: understand the issue statment and what it's trying to achieve
step 3: find the root cause of the issue in the given context from the repository
step 4: produce a list of edit suggestions that completely fixes the issue with the smallest safe changes.
"""

USER_PROMPT_ISSUES = """
TASK:
You will be provided with a github issue statement and its related context below, explaining a problem to resolve.
context can be files from code base or other simillar issues
I need you to solve this issue by generating a list of edit suggestions to ONLY a single file.
file_path_to_edit is the file path you decide to edit.
If you didn't reach a conclusion on what file to change, output an empty list in edits.

RULES FOR EACH EDIT (CRITICAL):
    - Do NOT modify tests or add new files; only edits to the given file.
    - Use the provided line numbers to set line_start_for_editing and line_end_for_editing as tightly as possible.
    - You MUST ONLY suggest edits that directly address the issue described.
    - you MUST ONLY suggest edits from the files given in the context.
    - exact_existing_buggy_snippet MUST exist in the chosen file.
    - exact_existing_buggy_snippet MUST be the smallest snippet that still uniquely identifies the change location.
    - line_start_for_editing and line_end_for_editing must tightly bound the region that contains exact_existing_buggy_snippet.
    - correct_replacement_snippet MUST be the full replacement for exact_existing_buggy_snippet.
    - correct_replacement_snippet must use the same indentation and style as surrounding code.
    - "DO NOT" put any code comment in correct_replacement_snippet.
    - evidence must reference specific diagnostic signals and the exact code symptom.
    - confidence should reflect likelihood the edit resolves the diagnostic (Any number from 0.0 to 1.0, 1 would be the highest confidence).

CATEGORY RULES:
- Use "SYNTAX_ERROR" when fixing parse/compile/runtime syntax issues (missing tokens, invalid indentation, unmatched brackets, etc.).
- Use "LINTING" when fixing style/static-analysis issues reported by a linter (unused imports/vars, typing warnings, etc.).
- Use "OTHER" when it's neither of the two categories

ESCAPING:
- Ensure exact_existing_buggy_snippet and correct_replacement_snippet are valid JSON strings (escape \\n, \\t, and quotes).

NOW: Produce the JSON object.
"""

USER_PROMPT_MULTIFILE_ZERO_SHOT = """
You will be provided with an issue statement explaining a problem to resolve, and related context from repository that can be files from code base or other simillar issues.
I need you to solve this issue by generating a single patch file that I can apply directly to this repository using git apply.
"""

USER_PROMPT_MULTIFILE_COT = USER_PROMPT_MULTIFILE_ZERO_SHOT + """
Follow the steps below to solve the issue:
step 1: UNDERSTAND ISSUE - Read the given issue description carefully.
step 2: IDENTIFY ROOT CAUSE - Analyze the provided file(s).
step 3: USE RETRIEVED CONTEXT - Consider related files and past issues for consistency
step 4: GENERATE PATCH - Produce a unified diff patch that completely resolves the issue with the smallest safe changes across multiple files.
"""
USER_PROMPT_V7 = """
TASK:
Given the file content and its related context below,
your task is to find any technical or quality issues in the file content.
Then, produce a list of edit suggestions that fix the issues.

RULES FOR EACH EDIT (CRITICAL):
    - Do NOT modify tests or add new files; only edits to the given file.
    - Use the provided line numbers to set line_start_for_editing and line_end_for_editing as tightly as possible.
    - exact_existing_buggy_snippet MUST be the smallest snippet that still uniquely identifies the change location.
    - exact_existing_buggy_snippet MUST match the file EXACTLY (including indentation, whitespace, punctuation, and newlines).
        - If you cannot make exact_existing_buggy_snippet match exactly, do not guess—choose a different, smaller region you can match.
    - line_start_for_editing and line_end_for_editing must tightly bound the region that contains exact_existing_buggy_snippet.
    - correct_replacement_snippet MUST be the full replacement for exact_existing_buggy_snippet.
    - correct_replacement_snippet must use the same indentation and style as surrounding code.
    - Do NOT put any comment in correct_replacement_snippet.
    - evidence must reference specific diagnostic signals and the exact code symptom.
    - confidence should reflect likelihood the edit resolves the diagnostic (Any number from 0.0 to 1.0, 1 would be the highest confidence).

CATEGORY RULES:
- Use "SYNTAX_ERROR" when fixing parse/compile/runtime syntax issues (missing tokens, invalid indentation, unmatched brackets, etc.).
- Use "LINTING" when fixing style/static-analysis issues reported by a linter (unused imports/vars, typing warnings, etc.).
- Use "OTHER" when it's neither of previous categories

ORDERING:
- Sort edits top-to-bottom by line_start_for_editing.

ESCAPING:
- Ensure exact_existing_buggy_snippet and correct_replacement_snippet are valid JSON strings (escape \\n, \\t, and quotes).

NOW: Produce the JSON object.
"""


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


# TODO: 
# - I need 1- simple 2- CoT 3- Zero-Shot 4- Few-Shot prompts
# - I need 1- Empty system and 2- Persona prompts

# USER_PROMPT_V4 = """
# Follow the steps below to improve the given submitted code
# step 1 - read the given code and its related context
# step 2 - find ONLY lines in the given code that will raise `syntax errors` in python
# step 3 - identify lines that need to be modified, added or deleted
# step 4 - generate ONLY the improved code without explanation
# """

# USER_PROMPT_V5 = """
# Follow the steps below
# step 1 - read the given code and its related context
# step 2 - find ONLY lines in the given code that contain `syntax errors` in python
# step 3 - output ONLY the line numbers that contain the defect with hard evidence that shows why they are syntax errors
# """
