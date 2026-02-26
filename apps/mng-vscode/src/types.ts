export interface MngAgent {
    id: string;
    name: string;
    type: string;
    state: string;
    branch: string | null;
    url: string | null;
    createTime: string;
    runtimeSeconds: number | null;
    host: MngAgentHost;
    labels: Record<string, string>;
}

export interface MngAgentHost {
    id: string;
    name: string;
    providerName: string;
    state: string;
}

export interface PrInfo {
    number: number;
    title: string;
    state: string;
    url: string;
    branch: string;
    isDraft: boolean;
    additions: number;
    deletions: number;
    reviewDecision: string | null;
}

export interface AgentSummary {
    totalAgents: number;
    runningAgents: number;
    openPRs: number;
}
