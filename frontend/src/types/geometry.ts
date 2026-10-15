export interface GeometryLine {
  id: string;
  page: number;
  points: number[][];
  line_type: string;
  reason: string;
  length: number;
}

export interface GeometryMeeting {
  id: string;
  page: number;
  position: number[];
  line_ids: string[];
  decision: string;
  reason: string;
  confidence: { level: "high" | "medium" | "low"; score: number; reason: string };
}

export interface FreeEndpoint {
  line_id: string;
  page: number;
  position: number[];
  reason: string;
}

export interface GeometryCoverage {
  total_length: number;
  explained_length: number;
  unexplained_length: number;
  free_endpoints: number;
  junctions: number;
  crossings: number;
  ambiguous: number;
}

export interface GeometryResult {
  lines: GeometryLine[];
  meetings: GeometryMeeting[];
  free_endpoints: FreeEndpoint[];
  coverage: GeometryCoverage;
}
