import type { CreateRunResponse, FixedFilesResponse, RunDetail, RunReport } from "@/types/run";

const apiRoot = "/api/tcr";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiRoot}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    let message = "请求失败，请稍后重试";
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export function createRun(data: FormData) {
  return requestJson<CreateRunResponse>("/runs", { method: "POST", body: data });
}

export function getRun(taskId: string, signal?: AbortSignal) {
  return requestJson<RunDetail>(`/runs/${encodeURIComponent(taskId)}`, { signal });
}

export function getReport(taskId: string) {
  return requestJson<RunReport>(`/runs/${encodeURIComponent(taskId)}/report`);
}

export function getFixedFiles(taskId: string) {
  return requestJson<FixedFilesResponse>(`/runs/${encodeURIComponent(taskId)}/fixed-files`);
}

export async function getPatch(taskId: string) {
  const response = await fetch(`${apiRoot}/runs/${encodeURIComponent(taskId)}/diff.patch`, { cache: "no-store" });
  if (!response.ok) throw new ApiError("Patch 获取失败", response.status);
  return response.text();
}

export function artifactUrl(taskId: string, path: string) {
  const safePath = path.split("/").map(encodeURIComponent).join("/");
  return `${apiRoot}/runs/${encodeURIComponent(taskId)}/artifacts/${safePath}`;
}
