import Link from "next/link";

export function AppHeader({ compact = false }: { compact?: boolean }) {
  return (
    <header className={`app-header ${compact ? "app-header--compact" : ""}`}>
      <Link href="/upload" className="brand" aria-label="返回上传页">
        <span className="brand__mark">T</span>
        <span>
          <strong>TCR Agent</strong>
          {!compact && <small>智能代码审查工作台</small>}
        </span>
      </Link>
      <div className="header-status"><span className="status-dot" /> FastAPI · 端口 8010</div>
    </header>
  );
}
