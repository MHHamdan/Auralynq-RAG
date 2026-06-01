// Server-side reverse proxy: forwards /api/* to the Auralynq backend and injects
// the bearer token from a server-only env var, so the browser never holds the API
// key (ADR-0012). Streams responses (SSE token streaming works transparently).
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_INTERNAL = (process.env.AURALYNQ_API_INTERNAL || "http://api:8000").replace(/\/$/, "");
const API_KEY = process.env.AURALYNQ_SERVE__API_KEY || "";

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const search = req.nextUrl.search || "";
  const target = `${API_INTERNAL}/${path.join("/")}${search}`;

  const headers = new Headers();
  // Forward content negotiation + type; drop hop-by-hop and host headers.
  for (const [k, v] of req.headers) {
    const key = k.toLowerCase();
    if (["host", "connection", "content-length", "accept-encoding"].includes(key)) continue;
    headers.set(k, v);
  }
  if (API_KEY) headers.set("Authorization", `Bearer ${API_KEY}`);

  const method = req.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);

  const init: RequestInit & { duplex?: "half" } = {
    method,
    headers,
    redirect: "manual",
  };
  if (hasBody) {
    init.body = req.body;
    init.duplex = "half"; // required by Node fetch when streaming a request body
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (e) {
    return new Response(
      JSON.stringify({ error: "bad_gateway", detail: String(e) }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  // Stream the upstream response straight back (SSE-friendly).
  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("content-length");
  return new Response(upstream.body, { status: upstream.status, headers: respHeaders });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
