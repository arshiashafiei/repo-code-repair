import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import * as cp from "child_process";
import { parseUnifiedDiff, applyPatch } from "./diffParser";
import { VirtualDocumentProvider } from "./virtualDocProvider";
import { INSTANCES, MODEL_NAME, PROJECTS_ROOT, RESULTS_PATH } from "./instanceData";
import { IssueTreeDataProvider, IssueNode } from "./treeDataProvider";

const SCHEME_ORIGINAL = "codefixer-original";
const SCHEME_MODIFIED = "codefixer-modified";

let originalProvider: VirtualDocumentProvider;
let modifiedProvider: VirtualDocumentProvider;
let treeDataProvider: IssueTreeDataProvider;

/**
 * Tracks the most recently viewed patch so it can be applied to disk.
 */
interface ActivePatchState {
  instanceId: string;
  projectPath: string;
  files: Array<{
    relativePath: string;
    modifiedContent: string;
  }>;
}

let activePatchState: ActivePatchState | null = null;

export function activate(context: vscode.ExtensionContext) {
  originalProvider = new VirtualDocumentProvider();
  modifiedProvider = new VirtualDocumentProvider();

  context.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider(SCHEME_ORIGINAL, originalProvider),
    vscode.workspace.registerTextDocumentContentProvider(SCHEME_MODIFIED, modifiedProvider),
    originalProvider,
    modifiedProvider
  );

  // ── Tree View ────────────────────────────────────────────────────────
  treeDataProvider = new IssueTreeDataProvider();
  const treeView = vscode.window.createTreeView("codefixer.issuesView", {
    treeDataProvider,
    showCollapseAll: true,
  });
  context.subscriptions.push(treeView);

  // ── Commands ─────────────────────────────────────────────────────────

  // View Diff – triggered from tree click (IssueNode arg) or command palette
  context.subscriptions.push(
    vscode.commands.registerCommand("codefixer.viewDiff", async (issueNode?: IssueNode) => {
      await viewDiffFlow(issueNode);
    })
  );

  // Apply all changes from the last viewed patch to the actual files on disk
  context.subscriptions.push(
    vscode.commands.registerCommand("codefixer.applyPatch", async () => {
      await applyPatchToDisk();
    })
  );

  // Checkout any commit hash in a selected project
  context.subscriptions.push(
    vscode.commands.registerCommand("codefixer.checkoutCommit", async () => {
      await checkoutCommitFlow();
    })
  );

  // Refresh tree
  context.subscriptions.push(
    vscode.commands.registerCommand("codefixer.refresh", () => {
      treeDataProvider.refresh();
      vscode.window.showInformationMessage("Issue list refreshed.");
    })
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Existing helpers (unchanged logic)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Read the JSONL results file and find the patch for a given instance_id + model.
 */
function findPatch(resultsPath: string, instanceId: string, modelName: string): string | null {
  const content = fs.readFileSync(resultsPath, "utf-8");
  const lines = content.split("\n").filter((l) => l.trim());

  for (const line of lines) {
    try {
      const entry = JSON.parse(line);
      if (entry.instance_id === instanceId && entry.model_name_or_path === modelName) {
        return entry.model_patch || null;
      }
    } catch {
      continue;
    }
  }
  return null;
}

/**
 * Git checkout a specific commit in a project directory.
 * Returns true on success.
 */
function gitCheckout(projectPath: string, commit: string): { success: boolean; error?: string } {
  try {
    cp.execSync(`git checkout ${commit} --force`, {
      cwd: projectPath,
      stdio: "pipe",
      timeout: 30000,
    });
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}

/**
 * Read a file from the project directory.
 */
function readProjectFile(projectPath: string, filePath: string): string | null {
  const fullPath = path.join(projectPath, filePath);
  try {
    return fs.readFileSync(fullPath, "utf-8");
  } catch {
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  View Diff Flow
// ═══════════════════════════════════════════════════════════════════════════

async function viewDiffFlow(issueNode?: IssueNode) {
  // Check results file exists
  if (!fs.existsSync(RESULTS_PATH)) {
    vscode.window.showErrorMessage(`Results file not found: ${RESULTS_PATH}`);
    return;
  }

  let instance;

  if (issueNode) {
    // Triggered from tree view click
    instance = issueNode.instance;
  } else {
    // Triggered from command palette → show quick pick
    const items: (vscode.QuickPickItem & { instanceId: string })[] = INSTANCES.map((inst) => {
      const lastDash = inst.instanceId.lastIndexOf("-");
      const issueNum = inst.instanceId.slice(lastDash + 1);
      const project = inst.projectDir;
      return {
        label: `${project} #${issueNum}`,
        description: `commit ${inst.baseCommit.slice(0, 8)}`,
        instanceId: inst.instanceId,
      };
    });

    const selected = await vscode.window.showQuickPick(items, {
      title: "Select Issue",
      placeHolder: "Pick an issue to view its suggested fix",
      matchOnDescription: true,
    });

    if (!selected) {
      return;
    }

    instance = INSTANCES.find((i) => i.instanceId === selected.instanceId)!;
  }

  const projectPath = path.join(PROJECTS_ROOT, instance.projectDir);

  if (!fs.existsSync(projectPath)) {
    vscode.window.showErrorMessage(`Project directory not found: ${projectPath}`);
    return;
  }

  // Find patch from results
  const patch = findPatch(RESULTS_PATH, instance.instanceId, MODEL_NAME);
  if (!patch) {
    vscode.window.showErrorMessage(
      `No patch found for this issue in ${instance.projectDir}`
    );
    return;
  }

  // Parse the diff
  const filePatches = parseUnifiedDiff(patch);
  if (filePatches.length === 0) {
    vscode.window.showWarningMessage("Patch is empty or could not be parsed.");
    return;
  }

  // Git checkout to the base commit
  const shortCommit = instance.baseCommit.slice(0, 8);
  const checkoutResult = await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `Checking out ${instance.projectDir} @ ${shortCommit}…`,
      cancellable: false,
    },
    async () => {
      return gitCheckout(projectPath, instance.baseCommit);
    }
  );

  if (!checkoutResult.success) {
    vscode.window.showErrorMessage(
      `Git checkout failed for ${instance.projectDir}: ${checkoutResult.error}`
    );
    return;
  }

  // Reset active patch state for this new diff session
  const patchFiles: ActivePatchState["files"] = [];
  const issueNum = instance.instanceId.slice(instance.instanceId.lastIndexOf("-") + 1);

  // Show diff for each file in the patch
  for (const filePatch of filePatches) {
    const filePath = filePatch.newPath !== "/dev/null" ? filePatch.newPath : filePatch.oldPath;

    // Read original file from disk (after checkout)
    let originalContent: string;
    if (filePatch.oldPath === "/dev/null") {
      originalContent = ""; // new file
    } else {
      const content = readProjectFile(projectPath, filePatch.oldPath);
      if (content === null) {
        vscode.window.showWarningMessage(`Could not read file: ${filePatch.oldPath}`);
        continue;
      }
      originalContent = content;
    }

    // Apply patch to get modified content
    let modifiedContent: string;
    if (filePatch.newPath === "/dev/null") {
      modifiedContent = ""; // file deleted
    } else {
      modifiedContent = applyPatch(originalContent, filePatch.hunks);
    }

    // Track for later apply-to-disk
    patchFiles.push({
      relativePath: filePath,
      modifiedContent,
    });

    // Build URIs for virtual documents
    const ts = Date.now();
    const originalUri = vscode.Uri.parse(
      `${SCHEME_ORIGINAL}:${filePath}?instance=${instance.instanceId}&ts=${ts}`
    );
    const modifiedUri = vscode.Uri.parse(
      `${SCHEME_MODIFIED}:${filePath}?instance=${instance.instanceId}&ts=${ts}`
    );

    originalProvider.setContent(originalUri, originalContent);
    modifiedProvider.setContent(modifiedUri, modifiedContent);

    const diffTitle = `${instance.projectDir} #${issueNum}: ${filePath}`;
    await vscode.commands.executeCommand("vscode.diff", originalUri, modifiedUri, diffTitle);
  }

  // Store the active patch state for apply-to-disk
  activePatchState = {
    instanceId: instance.instanceId,
    projectPath,
    files: patchFiles,
  };

  vscode.window.showInformationMessage(
    `Showing diff for ${instance.projectDir} #${issueNum} — use "Apply All Changes" to write to disk.`
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Apply Patch to Disk
// ═══════════════════════════════════════════════════════════════════════════

async function applyPatchToDisk() {
  if (!activePatchState) {
    vscode.window.showWarningMessage("No patch is currently loaded. View a diff first.");
    return;
  }

  const { projectPath, files, instanceId } = activePatchState;
  const issueNum = instanceId.slice(instanceId.lastIndexOf("-") + 1);

  const confirm = await vscode.window.showWarningMessage(
    `Apply all changes (${files.length} file${files.length !== 1 ? "s" : ""}) to disk?`,
    { modal: true },
    "Apply"
  );

  if (confirm !== "Apply") {
    return;
  }

  let applied = 0;
  let failed = 0;

  for (const file of files) {
    const fullPath = path.join(projectPath, file.relativePath);
    try {
      // Ensure parent directory exists (for new files)
      const dir = path.dirname(fullPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(fullPath, file.modifiedContent, "utf-8");
      applied++;
    } catch (err: any) {
      vscode.window.showErrorMessage(`Failed to write ${file.relativePath}: ${err.message}`);
      failed++;
    }
  }

  if (failed === 0) {
    vscode.window.showInformationMessage(
      `Successfully applied changes to ${applied} file${applied !== 1 ? "s" : ""}.`
    );
  } else {
    vscode.window.showWarningMessage(
      `Applied ${applied} file${applied !== 1 ? "s" : ""}, ${failed} failed.`
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Checkout Commit (free-form)
// ═══════════════════════════════════════════════════════════════════════════

async function checkoutCommitFlow() {
  // Step 1: Pick a project
  const projectDirs = [...new Set(INSTANCES.map((i) => i.projectDir))].sort();

  const projectPick = await vscode.window.showQuickPick(
    projectDirs.map((dir) => ({
      label: dir,
      description: path.join(PROJECTS_ROOT, dir),
    })),
    {
      title: "Select Project",
      placeHolder: "Choose the project repository to checkout in",
    }
  );

  if (!projectPick) {
    return;
  }

  const projectPath = path.join(PROJECTS_ROOT, projectPick.label);

  if (!fs.existsSync(projectPath)) {
    vscode.window.showErrorMessage(`Project directory not found: ${projectPath}`);
    return;
  }

  // Step 2: Enter commit hash
  const commitHash = await vscode.window.showInputBox({
    title: "Commit Hash",
    prompt: "Enter the commit hash (or branch name) to checkout",
    placeHolder: "e.g. a1b2c3d or main",
    validateInput: (value) => {
      if (!value.trim()) {
        return "Please enter a commit hash or branch name.";
      }
      return null;
    },
  });

  if (!commitHash) {
    return;
  }

  const result = await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `Checking out ${projectPick.label} @ ${commitHash.trim().slice(0, 8)}…`,
      cancellable: false,
    },
    async () => {
      return gitCheckout(projectPath, commitHash.trim());
    }
  );

  if (result.success) {
    vscode.window.showInformationMessage(
      `Checked out ${projectPick.label} @ ${commitHash.trim().slice(0, 8)}`
    );
  } else {
    vscode.window.showErrorMessage(
      `Checkout failed: ${result.error}`
    );
  }
}

export function deactivate() {}
