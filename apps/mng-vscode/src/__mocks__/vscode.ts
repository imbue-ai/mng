export const TreeItemCollapsibleState = { None: 0, Collapsed: 1, Expanded: 2 };
export const ThemeColor = class { constructor(public id: string) {} };
export const ThemeIcon = class { constructor(public id: string, public color?: any) {} };
export class TreeItem {
    label?: string;
    description?: string;
    tooltip?: any;
    iconPath?: any;
    contextValue?: string;
    command?: any;
    collapsibleState?: number;
    constructor(label: string, collapsibleState?: number) {
        this.label = label;
        this.collapsibleState = collapsibleState;
    }
}
export class MarkdownString {
    value: string;
    constructor(value?: string) { this.value = value || ''; }
}
export const EventEmitter = class {
    event = () => {};
    fire() {}
    dispose() {}
};
export const StatusBarAlignment = { Left: 1, Right: 2 };
export const window = {
    createTreeView: () => ({ dispose: () => {} }),
    createStatusBarItem: () => ({
        text: '',
        tooltip: '',
        command: '',
        show: () => {},
        dispose: () => {},
    }),
    createTerminal: () => ({ show: () => {}, sendText: () => {} }),
    showWarningMessage: async () => undefined,
    showInformationMessage: async () => undefined,
    showErrorMessage: async () => undefined,
    createOutputChannel: () => ({ appendLine: () => {}, show: () => {} }),
};
export const workspace = {
    getConfiguration: () => ({
        get: (key: string, defaultValue?: any) => defaultValue,
    }),
    workspaceFolders: [],
    onDidChangeConfiguration: () => ({ dispose: () => {} }),
};
export const commands = {
    registerCommand: () => ({ dispose: () => {} }),
    executeCommand: async () => {},
};
export const env = {
    openExternal: async () => true,
};
export const extensions = {
    getExtension: (_id: string) => undefined,
};
export const Uri = {
    parse: (s: string) => ({ toString: () => s }),
};
