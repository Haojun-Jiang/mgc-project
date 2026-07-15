"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AppHeader } from "@/components/AppHeader";
import { getRun } from "@/lib/task-api";
import type { RunDetail } from "@/types/run";

const agentCopy: Record<string, { title: string; description: string }> = {
  LLMTestGenerationAgent: { title: "规划与生成测试", description: "根据源码与需求推断关键测试场景" },
  TestAgent: { title: "执行测试与审查", description: "运行 pytest、语法检查和 AI 代码审查" },
  ReportAgent: { title: "归集风险报告", description: "整理问题、证据、根因与修复建议" },
  FixAgent: { title: "生成沙箱修复", description: "输出修复后文件和 unified diff" },
};

export default function ProcessingPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let stopped = false;
    let timeout: number | undefined;
    const controller = new AbortController();

    async function poll() {
      try {
        const detail = await getRun(taskId, controller.signal);
        if (stopped) return;
        setRun(detail);
        setError("");
        if (detail.status === "completed") {
          window.setTimeout(() => router.replace(`/result/${taskId}`), 650);
          return;
        }
        if (detail.status === "failed") return;
        timeout = window.setTimeout(poll, document.hidden ? 8000 : 3000);
      } catch (reason) {
        if (stopped) return;
        setError(reason instanceof Error ? reason.message : "无法获取任务状态");
        timeout = window.setTimeout(poll, 5000);
      }
    }

    poll();
    return () => {
      stopped = true;
      controller.abort();
      if (timeout) window.clearTimeout(timeout);
    };
  }, [router, taskId]);

  const steps = useMemo(() => run?.steps?.length ? run.steps : Object.keys(agentCopy).map((agent) => ({ agent, status: "pending" as const })), [run]);
  const completed = steps.filter((step) => ["completed", "passed", "skipped"].includes(step.status)).length;
  const progress = run?.status === "completed" ? 100 : run?.status === "running" ? Math.max(18, completed * 25) : 8;
  const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const seconds = String(elapsed % 60).padStart(2, "0");

  return (
    <main className="page page--processing">
      <AppHeader />
      <section className="processing-shell">
        <div className={`agent-orb ${run?.status === "failed" ? "agent-orb--failed" : ""}`}><span>T</span><i /><i /><i /></div>
        <div className="eyebrow"><span /> AGENT WORKING</div>
        <h1>{run?.status === "failed" ? "检测任务未能完成" : run?.status === "completed" ? "检测完成，正在进入报告" : "Agent 正在检查你的代码"}</h1>
        <p>{run?.status === "failed" ? "请查看失败原因后重新提交。" : "测试、审查、报告和沙箱修复正在依次执行，请保持页面打开。"}</p>

        <div className="task-meta">
          <span>任务 ID</span><code>{taskId}</code><span className="task-meta__divider" /><span>已用时</span><strong>{minutes}:{seconds}</strong>
        </div>

        <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>

        <div className="agent-steps">
          {steps.map((step, index) => {
            const done = ["completed", "passed", "skipped"].includes(step.status);
            const active = run?.status === "running" && step.status === "running";
            const copy = agentCopy[step.agent] || { title: step.agent, description: "Agent 正在处理" };
            return (
              <div className={`agent-step ${done ? "agent-step--done" : ""} ${active ? "agent-step--active" : ""}`} key={step.agent}>
                <div className="agent-step__number">{done ? "✓" : String(index + 1).padStart(2, "0")}</div>
                <div><strong>{copy.title}</strong><span>{copy.description}</span></div>
                <small>{done ? "已完成" : active ? "处理中" : "等待中"}</small>
              </div>
            );
          })}
        </div>
        {run?.status === "running" && completed === 0 && <div className="progress-note">当前后端仅返回整体运行状态，任务完成后将同步各阶段结果。</div>}

        {(error || run?.status === "failed") && (
          <div className="processing-error">
            <strong>任务失败</strong><span>{run?.summary || error}</span>
            <Link href="/upload">重新上传</Link>
          </div>
        )}
        {elapsed > 600 && run?.status !== "completed" && <div className="timeout-note">任务执行时间较长，你可以稍后使用当前地址继续查看。</div>}
      </section>
    </main>
  );
}
