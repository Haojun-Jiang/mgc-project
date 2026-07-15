export type RunStatus = "queued" | "running" | "completed" | "failed" | "unknown";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "passed" | "skipped" | "unknown";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface CodeFile {
  path: string;
  content: string;
  language?: string;
}

export interface RunStep {
  agent: string;
  status: StepStatus;
}

export interface RunLinkMap {
  self: string;
  report: string;
  patch: string;
  fixed_files: string;
}

export interface RunResultPayload {
  project?: { files?: CodeFile[] };
  generated_test_result?: { test_files?: CodeFile[]; warnings?: string[] };
  errors?: string[];
}

export interface RunDetail {
  run_id: string;
  status: RunStatus;
  steps: RunStep[];
  summary: string;
  result: RunResultPayload | null;
  links: RunLinkMap;
}

export interface CreateRunResponse {
  run_id: string;
  status: "queued";
  links: RunLinkMap;
}

export interface ReportIssue {
  issue_id: string;
  source: string;
  type: string;
  severity: Severity;
  confidence: number;
  file: string;
  line_start: number | null;
  line_end: number | null;
  evidence: string;
  root_cause: string;
  recommendation: string;
}

export interface RunReport {
  agent?: string;
  status?: string;
  summary: string;
  issues: ReportIssue[];
  risk_level: Severity;
  should_fix: boolean;
  llm_used: boolean;
  warnings: string[];
}

export interface FixedFilesResponse {
  files: CodeFile[];
}
