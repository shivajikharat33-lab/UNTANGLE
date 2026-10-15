export type PdfVerdict = "VECTOR" | "SCANNED" | "MIXED";

export interface StoredFile {
  stored_name: "original.pdf" | "io_list.xlsx";
  original_name: string;
  sha256: string;
  byte_size: number;
}

export interface SheetSummary {
  name: string;
  columns: string[];
  row_count: number;
}

export interface IntakeSummary {
  pdf: StoredFile;
  io_list: StoredFile;
  page_count: number;
  verdict: PdfVerdict;
  verdict_reason: string;
  sheets: SheetSummary[];
  warnings: string[];
}

export interface JobListItem {
  id: string;
  name: string;
  created_at: string;
  status: "uploaded";
  pdf_verdict: PdfVerdict;
  page_count: number;
}

export interface PublicConfig {
  max_upload_mb: number;
  modify_enabled?: boolean;
}
