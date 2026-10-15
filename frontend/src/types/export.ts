export type ExportFormat = "svg" | "pdf" | "png" | "json" | "excel";

export interface ExportMetadata {
  id: string;
  job_id: string;
  version_number: number;
  format: ExportFormat;
  filename: string;
  created_at: string;
  media_type: string;
  byte_size: number | null;
}
