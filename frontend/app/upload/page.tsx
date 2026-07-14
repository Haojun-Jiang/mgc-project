"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AppHeader } from "@/components/AppHeader";
import { ArrowRightIcon, FileIcon } from "@/components/Icons";
import { ApiError, createRun } from "@/lib/task-api";

const MAX_SIZE = 2 * 1024 * 1024;

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [requirement, setRequirement] = useState("");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [advanced, setAdvanced] = useState({ aiReview: true, generateTests: true, reportLlm: true, autoFix: true });

  function addFiles(incoming: File[]) {
    setError("");
    const existing = new Set(files.map((file) => file.name));
    for (const file of incoming) {
      if (!file.name.endsWith(".py")) return setError(`仅支持 .py 文件：${file.name}`);
      if (file.size > MAX_SIZE) return setError(`${file.name} 超过 2 MB`);
      if (existing.has(file.name)) return setError(`文件名重复：${file.name}`);
      existing.add(file.name);
    }
    setFiles((current) => [...current, ...incoming]);
  }

  async function submit() {
    if (!files.length) return setError("请至少选择一个 Python 文件");
    setSubmitting(true);
    setError("");
    const data = new FormData();
    files.forEach((file) => data.append("files", file));
    data.append("requirement", requirement);
    data.append("ai_review", String(advanced.aiReview));
    data.append("llm_generate_tests", String(advanced.generateTests));
    data.append("report_use_llm", String(advanced.reportLlm));
    data.append("auto_fix", String(advanced.autoFix));
    data.append("fix_target_severities", "critical,high,medium");
    try {
      const result = await createRun(data);
      router.push(`/processing/${result.run_id}`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "任务创建失败，请检查后端服务");
      setSubmitting(false);
    }
  }

  return (
    <main className="page page--upload">
      <AppHeader />
      <section className="upload-hero">
        <div className="eyebrow"><span /> CODE REVIEW AGENT</div>
        <h1>让每一次代码提交，<br /><em>都经过可靠验证。</em></h1>
        <p>上传 Python 源码与测试文件，Agent 将自动生成测试、执行检查、分析风险并给出可下载的修复方案。</p>
      </section>

      <section className="upload-card">
        <div className="step-label"><span>01</span> 选择待审查代码</div>
        <div
          className={`dropzone ${dragging ? "dropzone--active" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(Array.from(event.dataTransfer.files)); }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".py,text/x-python" multiple hidden onChange={(event) => addFiles(Array.from(event.target.files || []))} />
          <div className="dropzone__icon">＋</div>
          <strong>拖拽 Python 文件到这里，或点击选择</strong>
          <span>支持多个 .py 文件，单个文件不超过 2 MB</span>
        </div>

        {files.length > 0 && (
          <div className="selected-files">
            {files.map((file) => (
              <div className="selected-file" key={file.name}>
                <span className="selected-file__icon"><FileIcon /></span>
                <span><strong>{file.name}</strong><small>{(file.size / 1024).toFixed(1)} KB</small></span>
                <button type="button" onClick={() => setFiles((current) => current.filter((item) => item.name !== file.name))} aria-label={`移除 ${file.name}`}>×</button>
              </div>
            ))}
          </div>
        )}

        <div className="step-label step-label--second"><span>02</span> 描述预期行为 <small>可选</small></div>
        <textarea value={requirement} onChange={(event) => setRequirement(event.target.value)} placeholder="例如：calculate_discount 应根据会员等级返回正确折扣，结果不得小于 0……" />

        <details className="advanced-options">
          <summary>高级检测配置 <span>默认已开启完整流程</span></summary>
          <div className="option-grid">
            {([
              ["aiReview", "AI 代码审查", "识别安全性与可维护性风险"],
              ["generateTests", "自动生成测试", "无测试文件时推断并生成 pytest"],
              ["reportLlm", "智能报告增强", "生成根因分析和修复建议"],
              ["autoFix", "沙箱自动修复", "生成修复文件与 patch，不覆盖源码"],
            ] as const).map(([key, title, description]) => (
              <label className="option" key={key}>
                <span><strong>{title}</strong><small>{description}</small></span>
                <input type="checkbox" checked={advanced[key]} onChange={(event) => setAdvanced({ ...advanced, [key]: event.target.checked })} />
              </label>
            ))}
          </div>
        </details>

        {error && <div className="error-banner">{error}</div>}
        <div className="submit-row">
          <span>文件仅用于本次沙箱检测，不会修改原始代码</span>
          <button className="primary-button" type="button" disabled={submitting} onClick={submit}>
            {submitting ? "正在创建任务…" : <>开始智能检测 <ArrowRightIcon /></>}
          </button>
        </div>
      </section>
    </main>
  );
}
