import type { HealthResponse } from "../types/health";
import { ApiError, apiFetch, readErrorBody } from "./client";

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    record.status === "ok" &&
    typeof record.version === "string" &&
    record.version.length > 0 &&
    (record.database === "ok" || record.database === "failed") &&
    typeof record.time === "string"
  );
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await apiFetch("/api/health", signal);
  if (!response.ok) {
    const body = await readErrorBody(response);
    throw new ApiError(body?.message ?? "The health check failed.", response.status, body);
  }
  const payload: unknown = await response.json();
  if (!isHealthResponse(payload)) {
    throw new ApiError("The health check returned an unexpected body.", response.status, null);
  }
  return payload;
}
