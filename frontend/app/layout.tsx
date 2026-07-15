import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TCR Agent · 智能代码审查",
  description: "上传 Python 代码，自动完成测试、审查、报告与沙箱修复。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
