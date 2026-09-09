/**
 * Local data helpers – reads results and issues from disk.
 * No API calls, no LLM calls.
 */

import * as fs from "fs";
import * as path from "path";
import * as readline from "readline";
import { execSync, exec } from "child_process";

// ── Workspace root (the FP directory) ───────────────────────────────────

let WORKSPACE_ROOT = "";

export function setWorkspaceRoot(root: string) {
  WORKSPACE_ROOT = root;
}

export function getWorkspaceRoot(): string {
  return WORKSPACE_ROOT;
}

// ── Types ───────────────────────────────────────────────────────────────

export interface ResultRecord {
  instance_id: string;
  model_name_or_path: string;
  model_patch: string;
  exact_match: number;
  edit_similarity: number;
  bleu4: number;
  file_match: number;
  hunk_overlap: number;
  hunk_count_delta: number;
  model_added: number;
  model_removed: number;
  gold_added: number;
  gold_removed: number;
  lines_changed_ratio: number;
  patch_applicable: number;
  attempt_number: number;
  latency_s: number;
}

export interface IssueRecord {
  repo: string;
  number: number;
  title: string;
  body: string;
  state: string;
  created_at: string;
  labels: string[];
  html_url: string;
  discussion_summary?: string;
}

// ── Parse instance_id ───────────────────────────────────────────────────

export function parseInstanceId(instanceId: string): {
  owner: string;
  repoName: string;
  issueNumber: number;
} {
  // e.g. "sqlfluff__sqlfluff-1625" → owner=sqlfluff, repo=sqlfluff, issue=1625
  // e.g. "marshmallow-code__marshmallow-1343"
  const parts = instanceId.split("__");
  if (parts.length !== 2) {
    throw new Error(`Invalid instance_id format: ${instanceId}`);
  }
  const owner = parts[0];
  const rest = parts[1]; // "sqlfluff-1625" or "marshmallow-1343"
  // Issue number is the last dash-separated segment that is a pure number
  const segments = rest.split("-");
  const issueNumber = parseInt(segments[segments.length - 1], 10);
  const repoName = segments.slice(0, -1).join("-");
  return { owner, repoName, issueNumber };
}

// ── Load all results from JSONL ─────────────────────────────────────────

export function loadAllResults(): ResultRecord[] {
  const filePath = path.join(WORKSPACE_ROOT, "results", "swe_bench_lite_results.jsonl");
  if (!fs.existsSync(filePath)) {
    return [];
  }
  const content = fs.readFileSync(filePath, "utf-8");
  const records: ResultRecord[] = [];
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) { continue; }
    try {
      records.push(JSON.parse(trimmed));
    } catch {
      // skip malformed lines
    }
  }
  return records;
}

/** Get all unique instance_ids */
export function listInstanceIds(): string[] {
  const all = loadAllResults();
  return [...new Set(all.map((r) => r.instance_id))].sort();
}

/** Get all model names for a given instance_id */
export function listModelsForInstance(instanceId: string): string[] {
  const all = loadAllResults();
  return [
    ...new Set(
      all.filter((r) => r.instance_id === instanceId).map((r) => r.model_name_or_path)
    ),
  ].sort();
}

/** Get a specific result */
export function getResult(
  instanceId: string,
  model: string
): ResultRecord | undefined {
  const all = loadAllResults();
  return all.find(
    (r) => r.instance_id === instanceId && r.model_name_or_path === model
  );
}

// ── Load issue from local JSONL ─────────────────────────────────────────

export function findIssue(
  owner: string,
  repoName: string,
  issueNumber: number
): IssueRecord | undefined {
  // Look in issues/<owner>/ or issues/<repoName>/
  const searchDirs = [
    path.join(WORKSPACE_ROOT, "issues", owner),
    path.join(WORKSPACE_ROOT, "issues", repoName),
    path.join(WORKSPACE_ROOT, "issues", `${owner}__${repoName}`),
  ];

  for (const dir of searchDirs) {
    if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
      continue;
    }
    const files = fs.readdirSync(dir).filter((f) => f.endsWith(".jsonl")).sort();
    for (const file of files) {
      const content = fs.readFileSync(path.join(dir, file), "utf-8");
      for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed) { continue; }
        try {
          const rec = JSON.parse(trimmed) as IssueRecord;
          if (rec.number === issueNumber) {
            return rec;
          }
        } catch {
          // skip
        }
      }
    }
  }

  // Also check issues/<owner>-<repoName>/ pattern  (e.g. pylint-dev)
  // and the flat issues/*.jsonl
  const flatDir = path.join(WORKSPACE_ROOT, "issues");
  const flatFiles = fs
    .readdirSync(flatDir)
    .filter((f) => f.endsWith(".jsonl"));
  for (const file of flatFiles) {
    const content = fs.readFileSync(path.join(flatDir, file), "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) { continue; }
      try {
        const rec = JSON.parse(trimmed) as IssueRecord;
        if (rec.number === issueNumber) {
          return rec;
        }
      } catch {
        // skip
      }
    }
  }

  return undefined;
}

// ── Extract files from patch ────────────────────────────────────────────

export function extractFilesFromPatch(patch: string): string[] {
  const files: string[] = [];
  for (const line of patch.split("\n")) {
    const match = line.match(/^diff --git a\/(.+?) b\//);
    if (match) {
      files.push(match[1]);
    }
  }
  return [...new Set(files)];
}

// ── Get project path ───────────────────────────────────────────────────

export function getProjectPath(repoName: string): string {
  return path.join(WORKSPACE_ROOT, "projects", repoName);
}

// ── Git checkout ────────────────────────────────────────────────────────

export function gitCheckout(
  projectPath: string,
  commitHash: string
): { success: boolean; message: string } {
  try {
    execSync(`git checkout -f ${commitHash}`, {
      cwd: projectPath,
      stdio: "pipe",
      timeout: 30000,
    });
    return { success: true, message: `Checked out ${commitHash.slice(0, 7)}` };
  } catch (err: any) {
    return {
      success: false,
      message: err.stderr?.toString() || err.message,
    };
  }
}

// ── Git apply (dry-run check) ───────────────────────────────────────────

export function gitApplyCheck(
  projectPath: string,
  patch: string
): { appliesCleanly: boolean; message: string } {
  const tmpFile = path.join(projectPath, ".tmp_patch.diff");
  try {
    fs.writeFileSync(tmpFile, patch);
    execSync(
      `git apply --check --ignore-whitespace --recount "${tmpFile}"`,
      { cwd: projectPath, stdio: "pipe", timeout: 10000 }
    );
    return { appliesCleanly: true, message: "Patch applies cleanly" };
  } catch (err: any) {
    return {
      appliesCleanly: false,
      message: err.stderr?.toString() || err.message,
    };
  } finally {
    try { fs.unlinkSync(tmpFile); } catch { /* ignore */ }
  }
}

// ── Git apply (real apply) ──────────────────────────────────────────────

export function gitApply(
  projectPath: string,
  patch: string
): { success: boolean; message: string } {
  const tmpFile = path.join(projectPath, ".tmp_patch.diff");
  try {
    fs.writeFileSync(tmpFile, patch);
    execSync(
      `git apply --ignore-whitespace --recount "${tmpFile}"`,
      { cwd: projectPath, stdio: "pipe", timeout: 10000 }
    );
    return { success: true, message: "Patch applied successfully" };
  } catch (err: any) {
    return {
      success: false,
      message: err.stderr?.toString() || err.message,
    };
  } finally {
    try { fs.unlinkSync(tmpFile); } catch { /* ignore */ }
  }
}

// ── File tree (simple) ──────────────────────────────────────────────────

export function getFileTree(projectPath: string, maxDepth = 3): string {
  try {
    const result = execSync(
      `find . -maxdepth ${maxDepth} -type f | head -80 | sort`,
      { cwd: projectPath, stdio: "pipe", timeout: 5000 }
    );
    return result.toString().trim();
  } catch {
    return "(file tree unavailable)";
  }
}

// ── Get file content (for skeleton preview) ─────────────────────────────

export function readFileContent(filePath: string): string {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return "(file not found)";
  }
}
