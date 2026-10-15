import type { ErrorResponse } from "../types/errors";
import type { Job } from "../types/job";
import type { JobListItem, PublicConfig } from "../types/intake";
import type { ExtractionResult } from "../types/extraction";
import type { DetectionResult } from "../types/detections";
import type { GeometryResult } from "../types/geometry";
import type { DiagramGraph, GraphSummary, Pattern } from "../types/graph";
import type { Finding } from "../types/rules";
import type { CoverageMetric, LedgerPage, VerificationStatus } from "../types/coverage";
import type { SketchMeta } from "../types/sketch";
import type { TagReport } from "../types/reports";
import type { IoListResult, IoValidateRequest } from "../types/ioList";
import { ApiError, apiBaseUrl, apiFetch, apiSend, isErrorResponse, readErrorBody } from "./client";

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

export async function acceptOriginal(id: string): Promise<void> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/versions/accept`, "POST", {});
  if (!response.ok) {
    throw new ApiError("Version 0 could not be accepted.", response.status, await readErrorBody(response));
  }
}

export async function openDraft(id: string): Promise<void> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/draft`, "POST", {});
  if (!response.ok) {
    throw new ApiError("The working copy could not be opened.", response.status, await readErrorBody(response));
  }
}

export async function getDraft(id: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/draft`, signal);
  if (!response.ok) {
    throw new ApiError("There is no working copy.", response.status, await readErrorBody(response));
  }
  return response.json() as Promise<Record<string, unknown>>;
}

export async function postDraftOperation(id: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/draft/operations`, "POST", body);
  if (!response.ok) {
    throw new ApiError("The edit could not be applied.", response.status, await readErrorBody(response));
  }
  return response.json() as Promise<Record<string, unknown>>;
}

export async function undoDraft(id: string): Promise<void> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/draft/undo`, "POST", {});
  if (!response.ok) {
    throw new ApiError("Nothing to undo.", response.status, await readErrorBody(response));
  }
}

export async function redoDraft(id: string): Promise<void> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/draft/redo`, "POST", {});
  if (!response.ok) {
    throw new ApiError("Nothing to redo.", response.status, await readErrorBody(response));
  }
}

export async function saveDraft(id: string, note: string): Promise<void> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/draft/save`, "POST", { note });
  if (!response.ok) {
    throw new ApiError("The working copy could not be saved.", response.status, await readErrorBody(response));
  }
}

export async function listVersions(id: string, signal?: AbortSignal): Promise<Array<Record<string, unknown>>> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/versions`, signal);
  if (!response.ok) {
    throw new ApiError("Versions could not be loaded.", response.status, await readErrorBody(response));
  }
  return response.json() as Promise<Array<Record<string, unknown>>>;
}

export async function compareVersions(id: string, left: number, right: number, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/versions/compare?left=${left}&right=${right}`, signal);
  if (!response.ok) {
    throw new ApiError("Those versions could not be compared.", response.status, await readErrorBody(response));
  }
  return response.json() as Promise<Record<string, unknown>>;
}

export async function getUploadLimit(signal?: AbortSignal): Promise<PublicConfig> {
  const response = await apiFetch("/api/config", signal);
  return readJson(response, isPublicConfig);
}

export const getConfig = getUploadLimit;

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

function isIoList(value: unknown): value is IoListResult {
  return typeof value === "object" && value !== null && typeof (value as IoListResult).status === "string" && Array.isArray((value as IoListResult).rows);
}

export async function getIoList(id: string, signal?: AbortSignal): Promise<IoListResult> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/io-list`, signal);
  return readJson(response, isIoList);
}

export async function validateIoList(id: string, body: IoValidateRequest = {}): Promise<IoListResult> {
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/io-list/validate`, "POST", body);
  return readJson(response, isIoList);
}

function isExtraction(value: unknown): value is ExtractionResult {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ExtractionResult).status === "string" &&
    typeof (value as ExtractionResult).summary === "object"
  );
}

export async function getExtraction(id: string, signal?: AbortSignal): Promise<ExtractionResult> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/extraction`, signal);
  return readJson(response, isExtraction);
}

function isSketchMeta(value: unknown): value is SketchMeta {
  return typeof value === "object" && value !== null && typeof (value as SketchMeta).hidden_count === "number" && typeof (value as SketchMeta).disclaimer === "string";
}

export async function getSketchMeta(id: string, signal?: AbortSignal): Promise<SketchMeta> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/sketch/meta`, signal);
  return readJson(response, isSketchMeta);
}

export async function getSketchText(id: string, draft: boolean, signal?: AbortSignal): Promise<string> {
  const path = draft ? `/api/jobs/${encodeURIComponent(id)}/sketch/draft` : `/api/jobs/${encodeURIComponent(id)}/sketch`;
  const response = await apiFetch(path, signal);
  if (!response.ok) {
    const body = await readErrorBody(response);
    throw new ApiError(body?.message ?? "The sketch could not be loaded.", response.status, body);
  }
  return response.text();
}

export async function processJob(id: string, options?: { force?: boolean; retry?: boolean }): Promise<Job> {
  const params = new URLSearchParams();
  if (options?.force) {
    params.set("force", "true");
  }
  if (options?.retry) {
    params.set("retry", "true");
  }
  const query = params.toString();
  const response = await apiSend(`/api/jobs/${encodeURIComponent(id)}/process${query ? `?${query}` : ""}`, "POST", {});
  return readJson(response, isJob);
}

function isTagReport(value: unknown): value is TagReport {
  return typeof value === "object" && value !== null && Array.isArray((value as TagReport).rows) && typeof (value as TagReport).summary === "object";
}

function isDetections(value: unknown): value is DetectionResult {
  return typeof value === "object" && value !== null && Array.isArray((value as DetectionResult).items);
}

function isGeometry(value: unknown): value is GeometryResult {
  return typeof value === "object" && value !== null && Array.isArray((value as GeometryResult).lines) && typeof (value as GeometryResult).coverage === "object";
}

function isGraphSummary(value: unknown): value is GraphSummary {
  return typeof value === "object" && value !== null && typeof (value as GraphSummary).nodes === "number" && typeof (value as GraphSummary).edges === "number";
}

function isDiagramGraph(value: unknown): value is DiagramGraph {
  return typeof value === "object" && value !== null && Array.isArray((value as DiagramGraph).nodes) && Array.isArray((value as DiagramGraph).edges);
}

function isPatternList(value: unknown): value is Pattern[] {
  return Array.isArray(value) && value.every((item) => typeof item === "object" && item !== null && typeof (item as Pattern).id === "string");
}

function isFindingList(value: unknown): value is Finding[] {
  return Array.isArray(value) && value.every((item) => typeof item === "object" && item !== null && typeof (item as Finding).id === "string");
}

function isFinding(value: unknown): value is Finding {
  return typeof value === "object" && value !== null && typeof (value as Finding).id === "string" && typeof (value as Finding).rule_id === "string";
}

function isCoverage(value: unknown): value is CoverageMetric[] {
  return Array.isArray(value) && value.every((item) => typeof item === "object" && item !== null && typeof (item as CoverageMetric).name === "string" && typeof (item as CoverageMetric).denominator === "number");
}

function isLedgerPage(value: unknown): value is LedgerPage {
  return typeof value === "object" && value !== null && Array.isArray((value as LedgerPage).items) && typeof (value as LedgerPage).total === "number";
}

function isVerification(value: unknown): value is VerificationStatus {
  const state = (value as VerificationStatus).state;
  return typeof value === "object" && value !== null && (state === "verified" || state === "not_verified" || state === "needs_review");
}

export async function getCoverage(id: string, signal?: AbortSignal): Promise<CoverageMetric[]> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/coverage`, signal);
  return readJson(response, isCoverage);
}

export async function getLedger(id: string, itemType: string, reasonCode: string, offset: number, signal?: AbortSignal): Promise<LedgerPage> {
  const params = new URLSearchParams({ offset: String(offset), limit: "25" });
  if (itemType) {
    params.set("item_type", itemType);
  }
  if (reasonCode) {
    params.set("reason_code", reasonCode);
  }
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/ledger?${params.toString()}`, signal);
  return readJson(response, isLedgerPage);
}

export async function getVerification(id: string, signal?: AbortSignal): Promise<VerificationStatus> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/verification`, signal);
  return readJson(response, isVerification);
}

export async function getFindings(id: string, signal?: AbortSignal): Promise<Finding[]> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/findings`, signal);
  return readJson(response, isFindingList);
}

export async function getFinding(id: string, findingId: string, signal?: AbortSignal): Promise<Finding> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/findings/${encodeURIComponent(findingId)}`, signal);
  return readJson(response, isFinding);
}

export async function getPatterns(id: string, signal?: AbortSignal): Promise<Pattern[]> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/patterns`, signal);
  return readJson(response, isPatternList);
}

export async function getGraphSummary(id: string, signal?: AbortSignal): Promise<GraphSummary> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/graph/summary`, signal);
  return readJson(response, isGraphSummary);
}

export interface ItemDetail {
  id: string;
  type: string;
  tag: string;
  confidence: { level: string; score: number; reason: string };
  certainty: string;
  evidence: { description: string }[];
  findings: string[];
  review_reasons: string[];
  needs_review: boolean;
  patterns: string[];
  io_status: string;
  original_ids: string[];
  bbox: { page: number; x: number; y: number; w: number; h: number } | null;
  direction: string;
  line_type: string;
}

export interface TraceResult {
  start_id: string;
  mode: string;
  depth: number;
  traced_ids: string[];
  stopped: string[];
  note: string;
}

function isItemDetail(value: unknown): value is ItemDetail {
  return typeof value === "object" && value !== null && typeof (value as ItemDetail).id === "string";
}

function isTraceResult(value: unknown): value is TraceResult {
  return typeof value === "object" && value !== null && Array.isArray((value as TraceResult).traced_ids);
}

export async function getItem(id: string, itemId: string, signal?: AbortSignal): Promise<ItemDetail> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/items/${encodeURIComponent(itemId)}`, signal);
  return readJson(response, isItemDetail);
}

export async function getTrace(id: string, itemId: string, mode: string, signal?: AbortSignal): Promise<TraceResult> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/trace?item_id=${encodeURIComponent(itemId)}&mode=${encodeURIComponent(mode)}`, signal);
  return readJson(response, isTraceResult);
}

export async function getGraph(id: string, signal?: AbortSignal): Promise<DiagramGraph> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/graph`, signal);
  return readJson(response, isDiagramGraph);
}

export async function getGeometry(id: string, signal?: AbortSignal): Promise<GeometryResult> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/geometry`, signal);
  return readJson(response, isGeometry);
}

export async function getDetections(id: string, signal?: AbortSignal): Promise<DetectionResult> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/detections`, signal);
  return readJson(response, isDetections);
}

export function pagePreviewUrl(id: string, page: number): string {
  return `${apiBaseUrl()}/api/jobs/${encodeURIComponent(id)}/pages/${page}`;
}

export async function getTagReport(id: string, signal?: AbortSignal): Promise<TagReport> {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(id)}/tag-report`, signal);
  return readJson(response, isTagReport);
}
