export interface ExtractionSummary {
  words: number;
  lines: number;
  polylines: number;
  shapes: number;
  circles: number;
  primitives_read: number;
  primitives_used: number;
  unused_primitives: number;
  vector_items: number;
  raster_items: number;
}

export interface ExtractionResult {
  status: string;
  message: string;
  meta: {
    pdf_sha256: string;
    page_count: number;
    duration_ms: number;
    pymupdf_version: string;
    coordinate_system: string;
  };
  summary: ExtractionSummary;
  pages?: { page: number; width: number; height: number }[];
}
