import type { ErrorResponse } from "../types/errors";
import type { Job } from "../types/job";
import type { JobListItem, PublicConfig } from "../types/intake";
import { ApiError, apiBaseUrl, apiFetch, isErrorResponse, readErrorBody } from "./client";

async function readJson<T>(response: Response, isExpected: (value: unknown) => value is T): Promise<T> {
  if (!response.ok) {
    const body = await readErrorBody(response);
    throw new ApiError(body?.message ?? "The request failed.", response.status, body);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("The API returned a response that was not JSON.", response.status, null);
  }
  if (!isExpected(payload)) {
    throw new ApiError("The API returned a response this page cannot read.", response.status, null);
  }
  return payload;
}

function isJobList(value: unknown): value is JobListItem[] {
  return Array.isArray(value) && value.every((item) => typeof item === "object" && item !== null && typeof item.id === "string");
}

function isJob(value: unknown): value is Job {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Job).id === "string" &&
    Array.isArray((value as Job).stages)
  );
}

function isPublicConfig(value: unknown): value is PublicConfig {
  return typeof value === "object" && value !== null && typeof (value as PublicConfig).max_upload_mb === "number";
}

export async function getUploadLimit(signal?: AbortSignal): Promise<PublicConfig> {
  const response = await apiFetch("/api/config", signal);
  return readJson(response, isPublicConfig);
}

export async function listJobs(signal?: AbortSignal): Promise<JobListItem[]> {
  const response = await apiFetch("/api/jobs", signal);
  return readJson(response, isJobList);
}

export async function getJob(id: string, signal?: AbortSignal): Promise<Job> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}`, signal);
  return readJson(response, isJob);
}

export type UploadInput = {
  name: string;
  pid: File;
  ioList: File;
};

export function uploadJob(input: UploadInput, onProgress: (loaded: number, total: number) => void): Promise<Job> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    const name = input.name.trim();
    if (name) {
      body.append("name", name);
    }
    body.append("pid_pdf", input.pid);
    body.append("io_list", input.ioList);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBaseUrl()}/api/jobs`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(event.loaded, event.total);
      }
    };
    xhr.onerror = () => {
      reject(new ApiError("The API is not reachable.", 0, null));
    };
    xhr.onload = () => {
      const payload: unknown = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300 && isJob(payload)) {
        resolve(payload);
        return;
      }
      const errorBody: ErrorResponse | null = isErrorResponse(payload) ? payload : null;
      reject(new ApiError(errorBody?.message ?? "The upload failed.", xhr.status, errorBody));
    };
    xhr.send(body);
  });
}
