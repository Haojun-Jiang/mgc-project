import type { NextRequest } from "next/server";

const backend = process.env.TCR_API_BASE_URL || "http://127.0.0.1:8010";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const sourceUrl = new URL(request.url);
  const targetUrl = `${backend.replace(/\/$/, "")}/${path.join("/")}${sourceUrl.search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const accept = request.headers.get("accept");
  if (contentType) headers.set("content-type", contentType);
  if (accept) headers.set("accept", accept);

  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });

  const outgoingHeaders = new Headers();
  for (const name of ["content-type", "content-disposition", "content-length"]) {
    const value = response.headers.get(name);
    if (value) outgoingHeaders.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outgoingHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
