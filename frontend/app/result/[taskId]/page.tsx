"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AppHeader } from "@/components/AppHeader";
import { DownloadIcon, FileIcon } from "@/components/Icons";
import { artifactUrl, getFixedFiles, getPatch, getReport, getRun } from "@/lib/task-api";
import type { CodeFile, ReportIssue, RunDetail, RunReport, Severity } from "@/types/run";

type ViewItem = { id: string; label: string; kind: "source" | "generated" | "repair" | "report" | "patch"; content: string; path?: string };
const severityOrder: Severity[] = ["critical", "high", "medium", "low", "info"];
const severityLabel: Record<Severity, string> = { critical: "严重", high: "高危", medium: "中危", low: "低危", info: "提示" };

export default function ResultPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [report, setReport] = useState<RunReport | null>(null);
  const [repairs, setRepairs] = useState<CodeFile[]>([]);
  const [patch, setPatch] = useState("");
  const [selectedId, setSelectedId] = useState("report");
  const [selectedIssue, setSelectedIssue] = useState<ReportIssue | null>(null);
  const [panel, setPanel] = useState<"issues" | "repairs">("issues");
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([getRun(taskId), getReport(taskId), getFixedFiles(taskId), getPatch(taskId)])
      .then(([runDetail, reportDetail, fixed, patchText]) => {
        if (!active) return;
        if (runDetail.status !== "completed") {
          router.replace(`/processing/${taskId}`);
          return;
        }
        setRun(runDetail); setReport(reportDetail); setRepairs(fixed.files); setPatch(patchText); setSelectedIssue(reportDetail.issues[0] || null);
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "结果加载失败"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [router, taskId]);

  const sources = run?.result?.project?.files || [];
  const generated = run?.result?.generated_test_result?.test_files || [];
  const items = useMemo<ViewItem[]>(() => [
    { id: "report", label: "检测报告", kind: "report", content: report ? JSON.stringify(report, null, 2) : "" },
    ...sources.map((file) => ({ id: `source:${file.path}`, label: file.path, path: file.path, kind: "source" as const, content: file.content })),
    ...generated.map((file) => ({ id: `generated:${file.path}`, label: file.path, path: file.path, kind: "generated" as const, content: file.content })),
    ...repairs.map((file) => ({ id: `repair:${file.path}`, label: file.path, path: file.path, kind: "repair" as const, content: file.content })),
    { id: "patch", label: "fix.patch", path: "fix.patch", kind: "patch", content: patch },
  ], [generated, patch, repairs, report, sources]);
  const selected = items.find((item) => item.id === selectedId) || items[0];
  const issues = (report?.issues || []).filter((issue) => severity === "all" || issue.severity === severity);
  const lineStart = selectedIssue && selected?.path === selectedIssue.file ? selectedIssue.line_start : null;

  function openIssue(issue: ReportIssue) {
    setSelectedIssue(issue);
    setPanel("issues");
    const source = items.find((item) => item.kind === "source" && item.path === issue.file);
    if (source) setSelectedId(source.id);
  }

  if (loading) return <main className="workspace-loading"><div className="loading-spinner" /><strong>正在加载检测结果</strong><span>正在整理报告、修复文件和 Patch…</span></main>;
  if (error) return <main className="workspace-error"><strong>结果加载失败</strong><p>{error}</p><Link href="/upload">返回上传页</Link></main>;

  return (
    <main className="result-workspace">
      <AppHeader compact />
      <div className="workspace-toolbar">
        <div><Link href="/upload">所有任务</Link><span>/</span><strong>{taskId}</strong></div>
        <div className="workspace-summary"><span className={`risk-pill risk-pill--${report?.risk_level || "info"}`}>{severityLabel[report?.risk_level || "info"]}风险</span><strong>{report?.issues.length || 0}</strong><span>个问题</span></div>
        <div className="workspace-actions"><Link href="/upload" className="secondary-button">新建检测</Link><a className="primary-button primary-button--small" href={artifactUrl(taskId, "fix.patch")}><DownloadIcon /> 下载 Patch</a></div>
      </div>

      <div className="workspace-grid">
        <aside className="file-sidebar">
          <div className="sidebar-title"><span>文件与产物</span><small>{sources.length + repairs.length + generated.length + 2}</small></div>
          <FileGroup title="报告" items={items.filter((item) => item.kind === "report")} selectedId={selectedId} onSelect={setSelectedId} />
          <FileGroup title="原始文件" items={items.filter((item) => item.kind === "source")} selectedId={selectedId} onSelect={setSelectedId} />
          {generated.length > 0 && <FileGroup title="生成测试" items={items.filter((item) => item.kind === "generated")} selectedId={selectedId} onSelect={setSelectedId} />}
          <FileGroup title="修复产物" items={items.filter((item) => item.kind === "repair" || item.kind === "patch")} selectedId={selectedId} onSelect={setSelectedId} empty="暂无修复产物" />
        </aside>

        <section className="viewer-panel">
          <div className="viewer-tabs"><div className="viewer-tab viewer-tab--active"><FileIcon /> {selected?.label}</div></div>
          <div className="viewer-meta">
            <div><span className={`file-kind file-kind--${selected?.kind}`}>{selected?.kind === "source" ? "SOURCE" : selected?.kind === "repair" ? "REPAIR" : selected?.kind === "patch" ? "DIFF" : selected?.kind === "report" ? "REPORT" : "TEST"}</span><span>{selected?.content.split("\n").length || 0} 行</span></div>
            {selected?.path && selected.kind !== "source" && selected.kind !== "generated" && <a href={artifactUrl(taskId, selected.path)}><DownloadIcon /> 下载</a>}
          </div>
          {selected?.kind === "report" ? <ReportOverview report={report!} onIssue={openIssue} /> : <CodeViewer content={selected?.content || ""} highlightLine={lineStart} empty={selected?.kind === "patch" ? "本次检测没有生成 Patch" : "文件内容为空"} />}
        </section>

        <aside className="inspector-panel">
          <div className="inspector-tabs">
            <button className={panel === "issues" ? "active" : ""} onClick={() => setPanel("issues")}>Issues <span>{report?.issues.length || 0}</span></button>
            <button className={panel === "repairs" ? "active" : ""} onClick={() => setPanel("repairs")}>Repairs <span>{repairs.length}</span></button>
          </div>
          {panel === "issues" ? (
            <>
              <div className="issue-filters">
                <button className={severity === "all" ? "active" : ""} onClick={() => setSeverity("all")}>全部</button>
                {severityOrder.map((level) => report?.issues.some((issue) => issue.severity === level) && <button className={severity === level ? "active" : ""} onClick={() => setSeverity(level)} key={level}>{severityLabel[level]}</button>)}
              </div>
              <div className="issue-list">
                {issues.length ? issues.map((issue) => <IssueCard key={issue.issue_id} issue={issue} selected={selectedIssue?.issue_id === issue.issue_id} onClick={() => openIssue(issue)} />) : <EmptyPanel title="没有匹配的问题" description="尝试切换风险等级筛选。" />}
              </div>
              {selectedIssue && <IssueDetail issue={selectedIssue} />}
            </>
          ) : (
            <div className="repair-list">
              {repairs.length ? repairs.map((file) => (
                <button key={file.path} onClick={() => setSelectedId(`repair:${file.path}`)}>
                  <span className="repair-icon">✓</span><span><strong>{file.path}</strong><small>沙箱修复文件 · {file.content.split("\n").length} 行</small></span><span>→</span>
                </button>
              )) : <EmptyPanel title="暂无修复文件" description="本次检测未应用自动修复，原始代码没有被修改。" />}
              {patch && <button onClick={() => setSelectedId("patch")}><span className="repair-icon repair-icon--patch">±</span><span><strong>fix.patch</strong><small>Unified diff 修复补丁</small></span><span>→</span></button>}
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}

function FileGroup({ title, items, selectedId, onSelect, empty }: { title: string; items: ViewItem[]; selectedId: string; onSelect: (id: string) => void; empty?: string }) {
  return <div className="file-group"><h3>{title}<span>{items.length}</span></h3>{items.length ? items.map((item) => <button className={item.id === selectedId ? "active" : ""} key={item.id} onClick={() => onSelect(item.id)}><FileIcon /><span title={item.label}>{item.label}</span></button>) : empty && <small className="file-group__empty">{empty}</small>}</div>;
}

function CodeViewer({ content, highlightLine, empty }: { content: string; highlightLine: number | null; empty: string }) {
  if (!content) return <div className="viewer-empty"><span>⌁</span><strong>{empty}</strong></div>;
  return <div className="code-viewer">{content.split("\n").map((line, index) => <div className={`code-line ${highlightLine === index + 1 ? "code-line--highlight" : ""}`} key={index}><span>{index + 1}</span><code>{line || " "}</code></div>)}</div>;
}

function ReportOverview({ report, onIssue }: { report: RunReport; onIssue: (issue: ReportIssue) => void }) {
  const counts = severityOrder.map((level) => ({ level, count: report.issues.filter((issue) => issue.severity === level).length })).filter((item) => item.count);
  return <div className="report-overview"><div className="report-heading"><div className={`report-score report-score--${report.risk_level}`}><strong>{report.issues.length}</strong><span>ISSUES</span></div><div><span className="eyebrow"><span /> ANALYSIS COMPLETE</span><h2>代码检测报告</h2><p>{report.summary || "检测已完成，未生成摘要。"}</p></div></div><div className="report-stats">{counts.length ? counts.map(({ level, count }) => <div key={level}><span className={`severity-dot severity-dot--${level}`} /><strong>{count}</strong><small>{severityLabel[level]}问题</small></div>) : <div><span className="severity-dot severity-dot--info" /><strong>0</strong><small>未发现问题</small></div>}</div>{report.warnings.length > 0 && <div className="report-warnings"><strong>运行提示</strong>{report.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}<h3 className="report-section-title">主要发现</h3><div className="report-issue-grid">{report.issues.slice(0, 6).map((issue) => <button key={issue.issue_id} onClick={() => onIssue(issue)}><span className={`severity-tag severity-tag--${issue.severity}`}>{severityLabel[issue.severity]}</span><strong>{issue.type || issue.issue_id}</strong><small>{issue.file}{issue.line_start ? `:${issue.line_start}` : ""}</small><p>{issue.evidence || issue.root_cause || "查看问题详情"}</p></button>)}{!report.issues.length && <EmptyPanel title="检测通过" description="当前检测范围内没有发现需要关注的问题。" />}</div></div>;
}

function IssueCard({ issue, selected, onClick }: { issue: ReportIssue; selected: boolean; onClick: () => void }) {
  return <button className={`issue-card ${selected ? "issue-card--selected" : ""}`} onClick={onClick}><div><span className={`severity-tag severity-tag--${issue.severity}`}>{severityLabel[issue.severity]}</span><small>{Math.round(issue.confidence * 100)}% 置信度</small></div><strong>{issue.type || issue.issue_id}</strong><span className="issue-location">{issue.file || "未知文件"}{issue.line_start ? `:${issue.line_start}` : ""}</span><p>{issue.evidence || issue.root_cause || "暂无问题证据"}</p></button>;
}

function IssueDetail({ issue }: { issue: ReportIssue }) {
  return <div className="issue-detail"><h3>问题详情</h3><dl><dt>根因分析</dt><dd>{issue.root_cause || "暂无根因分析"}</dd><dt>修复建议</dt><dd>{issue.recommendation || "暂无修复建议"}</dd><dt>来源</dt><dd>{issue.source || "unknown"} · {issue.issue_id}</dd></dl></div>;
}

function EmptyPanel({ title, description }: { title: string; description: string }) { return <div className="empty-panel"><span>✓</span><strong>{title}</strong><p>{description}</p></div>; }
