/**
 * CodeFixerPanel – manages the webview panel.
 *
 * All data is loaded from local files (results/, issues/, projects/).
 * No LLM or API calls.  Real operations: git checkout + git apply.
 */

import * as vscode from "vscode";
import * as path from "path";
import * as data from "./dataProvider";
import { getWebviewHtml } from "./webviewContent";

export class CodeFixerPanel {
  public static readonly viewType = "codeFixerRun";
  private static instance: CodeFixerPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private disposables: vscode.Disposable[] = [];

  private runCounter = 0;

  // ── Factory ───────────────────────────────────────────────────────────

  public static createOrShow(
    extensionUri: vscode.Uri,
    _context: vscode.ExtensionContext
  ) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    if (CodeFixerPanel.instance) {
      CodeFixerPanel.instance.panel.reveal(column);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      CodeFixerPanel.viewType,
      "Code Fixer",
      column || vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, "media"),
          vscode.Uri.joinPath(extensionUri, "out"),
        ],
      }
    );

    CodeFixerPanel.instance = new CodeFixerPanel(panel, extensionUri);
  }

  // ── Constructor ────────────────────────────────────────────────────────

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
    this.panel = panel;
    this.extensionUri = extensionUri;

    const instanceIds = data.listInstanceIds();
    this.panel.webview.html = getWebviewHtml(
      this.panel.webview,
      extensionUri,
      instanceIds
    );

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    this.panel.webview.onDidReceiveMessage(
      (msg) => this.handleMessage(msg),
      null,
      this.disposables
    );
  }

  public dispose() {
    CodeFixerPanel.instance = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      const d = this.disposables.pop();
      if (d) { d.dispose(); }
    }
  }

  private post(msg: Record<string, unknown>) {
    this.panel.webview.postMessage(msg);
  }

  private log(text: string) {
    this.post({ type: "log", text });
  }

  // ── Message handler ────────────────────────────────────────────────────

  private async handleMessage(msg: any) {
    switch (msg.type) {
      case "getModels":
        return this.cmdGetModels(msg.instanceId);
      case "runPipeline":
        return this.cmdRunPipeline(msg.instanceId, msg.model);
      case "applyPatch":
        return this.cmdApplyPatch(msg);
      case "rejectPatch":
        return this.cmdRejectPatch();
      case "checkout":
        return this.cmdCheckout(msg);
      default:
        this.log(`Unknown message type: ${msg.type}`);
    }
  }

  // ── Command: list models ───────────────────────────────────────────────

  private cmdGetModels(instanceId: string) {
    const models = data.listModelsForInstance(instanceId);
    this.post({ type: "modelsList", models });
  }

  // ── Command: checkout ──────────────────────────────────────────────────

  private cmdCheckout(msg: any) {
    const { repoName, commitHash } = msg;
    const projectPath = data.getProjectPath(repoName);
    this.log(`Checking out ${commitHash} in projects/${repoName}…`);
    this.post({ type: "status", stage: "checkout", state: "loading" });

    const result = data.gitCheckout(projectPath, commitHash);
    if (result.success) {
      this.post({ type: "status", stage: "checkout", state: "done" });
      this.log(`✓ ${result.message}`);
    } else {
      this.post({ type: "status", stage: "checkout", state: "error" });
      this.log(`✗ Checkout failed: ${result.message}`);
    }
  }

  // ── Command: run pipeline (all local) ──────────────────────────────────

  private cmdRunPipeline(instanceId: string, model: string) {
    this.runCounter++;
    const runId = `#${this.runCounter}`;
    this.post({ type: "runStarted", runId });
    this.log(`═══ Run ${runId}: ${instanceId} [${model}] ═══`);

    let parsed: ReturnType<typeof data.parseInstanceId>;
    try {
      parsed = data.parseInstanceId(instanceId);
    } catch (err: any) {
      this.log(`✗ ${err.message}`);
      return;
    }

    // Step 1: Load result
    this.post({ type: "status", stage: "result", state: "loading" });
    const result = data.getResult(instanceId, model);
    if (!result) {
      this.post({ type: "status", stage: "result", state: "error" });
      this.log(`✗ No result found for ${instanceId} + ${model}`);
      return;
    }
    this.post({ type: "status", stage: "result", state: "done" });
    this.log(`✓ Result loaded (patch_applicable=${result.patch_applicable}, bleu4=${result.bleu4})`);

    // Step 2: Load issue
    this.post({ type: "status", stage: "issue", state: "loading" });
    const issue = data.findIssue(parsed.owner, parsed.repoName, parsed.issueNumber);
    let issueText = "";
    if (issue) {
      issueText = [
        `#${issue.number}: ${issue.title}`,
        "",
        issue.body || "",
        issue.labels?.length ? `Labels: ${issue.labels.join(", ")}` : "",
        issue.discussion_summary ? `\nDiscussion Summary:\n${issue.discussion_summary}` : "",
      ].filter(Boolean).join("\n");
      this.post({ type: "issueLoaded", text: issueText, data: issue });
      this.post({ type: "status", stage: "issue", state: "done" });
      this.log(`✓ Issue #${issue.number}: ${issue.title}`);
    } else {
      issueText = `Issue #${parsed.issueNumber} (not found in local storage)`;
      this.post({ type: "issueLoaded", text: issueText });
      this.post({ type: "status", stage: "issue", state: "done" });
      this.log(`⚠ Issue #${parsed.issueNumber} not found locally`);
    }

    // Step 3: Extract files from patch
    this.post({ type: "status", stage: "selectFiles", state: "loading" });
    const selectedFiles = data.extractFilesFromPatch(result.model_patch);
    this.post({ type: "filesSelected", files: selectedFiles });
    this.post({ type: "status", stage: "selectFiles", state: "done" });
    this.log(`✓ Files from patch: ${selectedFiles.join(", ")}`);

    // Step 4: File skeleton
    this.post({ type: "status", stage: "skeleton", state: "loading" });
    const projectPath = data.getProjectPath(parsed.repoName);
    const tree = data.getFileTree(projectPath);
    this.post({ type: "fileTree", tree });

    let skeleton = "";
    for (const file of selectedFiles) {
      const fullPath = path.join(projectPath, file);
      const content = data.readFileContent(fullPath);
      const lines = content.split("\n").slice(0, 30);
      skeleton += `── ${file} ──\n${lines.join("\n")}\n…\n\n`;
    }
    this.post({ type: "skeletonLoaded", skeleton });
    this.post({ type: "status", stage: "skeleton", state: "done" });
    this.log("✓ File skeleton loaded");

    // Step 5: Context / metrics
    this.post({ type: "status", stage: "context", state: "loading" });
    const contextStr = [
      `Instance: ${instanceId}`,
      `Model: ${model}`,
      `Repo: ${parsed.owner}/${parsed.repoName}`,
      `Issue: #${parsed.issueNumber}`,
      "",
      "── Metrics ──",
      `  exact_match:        ${result.exact_match}`,
      `  edit_similarity:    ${result.edit_similarity}`,
      `  bleu4:              ${result.bleu4}`,
      `  file_match:         ${result.file_match}`,
      `  hunk_overlap:       ${result.hunk_overlap}`,
      `  hunk_count_delta:   ${result.hunk_count_delta}`,
      `  lines_changed_ratio: ${result.lines_changed_ratio}`,
      `  patch_applicable:   ${result.patch_applicable}`,
      `  attempt_number:     ${result.attempt_number}`,
      `  latency_s:          ${result.latency_s}s`,
      "",
      `  model_added:        ${result.model_added} lines`,
      `  model_removed:      ${result.model_removed} lines`,
      `  gold_added:         ${result.gold_added} lines`,
      `  gold_removed:       ${result.gold_removed} lines`,
    ].join("\n");
    this.post({ type: "contextLoaded", context: contextStr });
    this.post({ type: "status", stage: "context", state: "done" });
    this.log("✓ Context / metrics loaded");

    // Step 6: Show patch
    this.post({ type: "status", stage: "repair", state: "loading" });
    this.post({
      type: "patchGenerated",
      patch: result.model_patch,
      instanceId,
    });
    this.post({ type: "status", stage: "repair", state: "done" });
    this.log(`✓ Patch loaded (${result.model_added}+ / ${result.model_removed}−)`);

    // Step 7: git apply --check
    this.post({ type: "status", stage: "applyCheck", state: "loading" });
    const checkResult = data.gitApplyCheck(projectPath, result.model_patch);
    this.post({
      type: "applyCheckResult",
      appliesCleanly: checkResult.appliesCleanly,
      message: checkResult.message,
    });
    this.post({ type: "status", stage: "applyCheck", state: "done" });
    if (checkResult.appliesCleanly) {
      this.log("✓ Patch applies cleanly (git apply --check)");
    } else {
      this.log(`⚠ git apply errors: ${checkResult.message}`);
    }

    this.log(`═══ Run ${runId} finished ═══`);
  }

  // ── Command: apply patch (REAL) ────────────────────────────────────────

  private async cmdApplyPatch(msg: any) {
    const instanceId: string = msg.instanceId;
    const patchStr: string = msg.patch;

    let parsed: ReturnType<typeof data.parseInstanceId>;
    try {
      parsed = data.parseInstanceId(instanceId);
    } catch (err: any) {
      this.log(`✗ ${err.message}`);
      return;
    }

    const projectPath = data.getProjectPath(parsed.repoName);

    const answer = await vscode.window.showWarningMessage(
      `Apply this patch to projects/${parsed.repoName}?`,
      { modal: true },
      "Apply"
    );

    if (answer !== "Apply") {
      this.log("Patch application cancelled.");
      return;
    }

    this.log(`Applying patch to ${projectPath}…`);
    const result = data.gitApply(projectPath, patchStr);
    if (result.success) {
      this.log(`✓ ${result.message}`);
      vscode.window.showInformationMessage(
        `Patch applied to projects/${parsed.repoName}`
      );
    } else {
      this.log(`✗ Apply failed: ${result.message}`);
      vscode.window.showErrorMessage(`Patch apply failed: ${result.message}`);
    }
  }

  private async cmdRejectPatch() {
    this.log("Patch rejected by user.");
    vscode.window.showInformationMessage("Patch rejected.");
  }
}
