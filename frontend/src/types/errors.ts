/** The only error body the API returns. */
export interface ErrorResponse {
  error_code: string;
  message: string;
  details: Record<string, unknown> | null;
  request_id: string;
}
