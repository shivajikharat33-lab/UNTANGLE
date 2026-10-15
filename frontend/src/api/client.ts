import type { ErrorResponse } from "../types/errors";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_URL?.trim();
  const base = configured && configured.length > 0 ? configured : DEFAULT_API_URL;
  return base.replace(/\/$/, "");
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorResponse | null;

  constructor(message: string, status: number, body: ErrorResponse | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.error_code === "string" &&
    typeof record.message === "string" &&
    typeof record.request_id === "string" &&
    (record.details === null || (typeof record.details === "object" && record.details !== null))
  );
}

export async function apiSend(
  path: string,
  method: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  try {
    return await fetch(`${apiBaseUrl()}${path}`, {
      method,
      signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError("The API is not reachable.", 0, null);
  }
}

export async function apiFetch(path: string, signal?: AbortSignal): Promise<Response> {
  try {
    return await fetch(`${apiBaseUrl()}${path}`, {
      signal,
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError("The API is not reachable.", 0, null);
  }
}

export async function readErrorBody(response: Response): Promise<ErrorResponse | null> {
  try {
    const payload: unknown = await response.json();
    return isErrorResponse(payload) ? payload : null;
  } catch {
    return null;
  }
}
