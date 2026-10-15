/** Matches backend/app/schemas/health.py. */
export interface HealthResponse {
  status: "ok";
  version: string;
  database: "ok" | "failed";
  time: string;
}
