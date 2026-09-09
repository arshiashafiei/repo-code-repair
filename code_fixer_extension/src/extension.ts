/**
 * Code Fixer VS Code Extension – Main entry point.
 *
 * No LLM/API calls. All data is loaded from local results/ and issues/ dirs.
 * Real operations: git checkout + git apply in projects/.
 */

import * as vscode from "vscode";
import { CodeFixerPanel } from "./panel";
import { setWorkspaceRoot } from "./dataProvider";

export function activate(context: vscode.ExtensionContext) {
  // Determine workspace root
  const wsFolder = vscode.workspace.workspaceFolders?.[0];
  if (wsFolder) {
    setWorkspaceRoot(wsFolder.uri.fsPath);
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("codeFixer.newRun", () => {
      CodeFixerPanel.createOrShow(context.extensionUri, context);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("codeFixer.showPanel", () => {
      CodeFixerPanel.createOrShow(context.extensionUri, context);
    })
  );
}

export function deactivate() {}
