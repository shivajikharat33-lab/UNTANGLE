import type { ErrorResponse } from "../types/errors";

const DEFAULT_API_URL = "http://127.0.0.1:8000";
const TOKEN_KEY = "untangle.accessToken";

export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_URL;
  if (configured === undefined || configured === null) {
    return DEFAULT_API_URL;
  }
  const trimmed = String(configured).trim();
  if (trimmed === "" || trimmed === "/") {
    return "";
  }
  return trimmed.replace(/\/$/, "");
}

export function accessToken(): string {
  if (typeof sessionStorage === "undefined") {
    return "";
  }
  return sessionStorage.getItem(TOKEN_KEY) ?? "";
}

export function setAccessToken(token: string): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  if (typeof sessionStorage === "undefined") {
    return;
  }
  sessionStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = accessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function noteAccessFailure(body: ErrorResponse | null): void {
  if (body?.error_code !== "ACCESS_REQUIRED" || typeof window === "undefined") {
    return;
  }
  clearAccessToken();
  window.dispatchEvent(new Event("untangle-locked"));
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
      credentials: "include",
      headers: { Accept: "application/json", "Content-Type": "application/json", ...authHeaders() },
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
      credentials: "include",
      headers: { Accept: "application/json", ...authHeaders() },
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
    const body = isErrorResponse(payload) ? payload : null;
    noteAccessFailure(body);
    return body;
  } catch {
    return null;
  }
}
