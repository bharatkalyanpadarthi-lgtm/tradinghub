import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_BASE =
  process.env.TRADENEST_BACKEND_URL ??
  process.env.NEXT_PUBLIC_TRADENEST_API_BASE ??
  "http://127.0.0.1:8000";
const ADMIN_TOKEN =
  process.env.TRADENEST_ADMIN_TOKEN ??
  process.env.NEXT_PUBLIC_TRADENEST_ADMIN_TOKEN ??
  "";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`/${path.join("/")}`, BACKEND_BASE);
  targetUrl.search = incomingUrl.search;

  const headers = new Headers();
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  headers.set("x-tradenest-admin-token", ADMIN_TOKEN);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const backendResponse = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
    cache: "no-store"
  });

  return new NextResponse(await backendResponse.text(), {
    status: backendResponse.status,
    headers: {
      "content-type": backendResponse.headers.get("content-type") ?? "application/json"
    }
  });
}

export { proxy as GET, proxy as POST };
