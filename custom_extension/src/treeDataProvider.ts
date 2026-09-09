import * as vscode from "vscode";
import { INSTANCES, InstanceInfo } from "./instanceData";

/**
 * Represents a project folder node in the tree view.
 */
export class ProjectNode {
  constructor(
    public readonly projectDir: string,
    public readonly issues: InstanceInfo[]
  ) {}
}

/**
 * Represents an individual issue node in the tree view.
 */
export class IssueNode {
  constructor(public readonly instance: InstanceInfo) {}
}

export type TreeElement = ProjectNode | IssueNode;

/**
 * Tree data provider that groups available issues by project.
 * Displays a two-level hierarchy: Project → Issues.
 */
export class IssueTreeDataProvider implements vscode.TreeDataProvider<TreeElement> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeElement | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TreeElement): vscode.TreeItem {
    if (element instanceof ProjectNode) {
      const item = new vscode.TreeItem(
        element.projectDir,
        vscode.TreeItemCollapsibleState.Collapsed
      );
      item.iconPath = new vscode.ThemeIcon("repo");
      item.contextValue = "project";
      item.description = `${element.issues.length} issue${element.issues.length !== 1 ? "s" : ""}`;
      item.tooltip = `Project: ${element.projectDir}`;
      return item;
    }

    // IssueNode
    const inst = element.instance;
    const issueNum = inst.instanceId.slice(inst.instanceId.lastIndexOf("-") + 1);
    const item = new vscode.TreeItem(
      `Issue #${issueNum}`,
      vscode.TreeItemCollapsibleState.None
    );
    item.iconPath = new vscode.ThemeIcon("bug");
    item.contextValue = "issue";
    item.description = inst.baseCommit.slice(0, 8);
    item.tooltip = `Click to view the suggested fix\nBase commit: ${inst.baseCommit}`;
    item.command = {
      command: "codefixer.viewDiff",
      title: "View Diff",
      arguments: [element],
    };
    return item;
  }

  getChildren(element?: TreeElement): vscode.ProviderResult<TreeElement[]> {
    if (!element) {
      // Root level – group instances by project directory
      const projectMap = new Map<string, InstanceInfo[]>();
      for (const inst of INSTANCES) {
        if (!projectMap.has(inst.projectDir)) {
          projectMap.set(inst.projectDir, []);
        }
        projectMap.get(inst.projectDir)!.push(inst);
      }
      return Array.from(projectMap.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([dir, issues]) => new ProjectNode(dir, issues));
    }

    if (element instanceof ProjectNode) {
      return element.issues.map((inst) => new IssueNode(inst));
    }

    return [];
  }
}
