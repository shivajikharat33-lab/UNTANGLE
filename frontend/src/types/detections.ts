export interface DetectionEvidence {
  source: string;
  description: string;
  page: number | null;
}

export interface DetectionItem {
  id: string;
  kind: string;
  subtype: string;
  page: number;
  bbox: number[];
  label: string;
  tag: string;
  confidence: { level: "high" | "medium" | "low"; score: number; reason: string };
  evidence: DetectionEvidence[];
  source: string;
  direction: string | null;
}

export interface DetectionCensus {
  instrument: number;
  equipment: number;
  valve: number;
  arrow: number;
  unclassified: number;
  linked_to_io: number;
}

export interface DetectionPage {
  page: number;
  width: number;
  height: number;
}

export interface DetectionResult {
  items: DetectionItem[];
  pages: DetectionPage[];
  census: DetectionCensus;
}
