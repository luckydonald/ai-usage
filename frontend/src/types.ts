export interface Account {
  id: string;
  service: string;
  provider: string;
  name: string;
  enabled: boolean;
  colors: Record<string, string>;
}

export interface CatalogMetric {
  service: string;
  provider: string;
  account_id: string;
  metric_key: string;
  metric_name: string;
}

export interface Catalog {
  accounts: Account[];
  metrics: CatalogMetric[];
  exhausted_color: string;
}

export interface LatestMetric {
  event_id: string;
  service: string;
  provider: string;
  account_id: string;
  metric_key: string;
  metric_name: string;
  observed_at: string;
  reset_at: string | null;
  percentage: number;
  current: number | null;
  maximum: number | null;
  unit: string | null;
}

export interface GraphPoint {
  at: string;
  percentage: number;
  current: number | null;
  maximum: number | null;
}

export interface GraphWindow {
  start: string;
  end: string;
  maximum_percentage: number;
  exhausted_from: string | null;
  current: boolean;
  projected_end_percentage: number | null;
}

export interface GraphSeries {
  service: string;
  provider: string;
  account_id: string;
  metric_key: string;
  metric_name: string;
  color: string;
  points: GraphPoint[];
  windows: GraphWindow[];
}

export interface Filters {
  services: string[];
  providers: string[];
  accounts: string[];
  metrics: string[];
}

