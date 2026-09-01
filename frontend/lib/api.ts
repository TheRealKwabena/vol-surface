import type { VolSurfaceRequest, VolSurfaceResponse } from "./types";

export async function fetchVolSurface(req: VolSurfaceRequest): Promise<VolSurfaceResponse> {
  const res = await fetch("/api/backend/vol-surface", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed with status ${res.status}`);
  }

  return res.json();
}
