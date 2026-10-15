export interface SketchMeta {
  hidden_count: number;
  verified_label: boolean;
  failed_check: boolean;
  route_clear?: boolean;
  node_count?: number;
  edge_count?: number;
  crossing_count?: number;
  bend_count?: number;
  disclaimer: string;
  legend: string[];
  processing_version: string;
}
