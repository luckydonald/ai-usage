export interface AccountIdentity {
  name: string | null;
  email: string | null;
}

export interface SubscriptionStatus {
  plan_type: string | null;
  status: string | null;
  renews_at: string | null;
  cancel_at: string | null;
}

export interface Account {
  id: string;
  service: string;
  provider: string;
  name: string;
  enabled: boolean;
  colors: Record<string, string>;
  identity: AccountIdentity | null;
  subscription: SubscriptionStatus | null;
  group_id: string | null;
}

export interface CatalogMetric {
  service: string;
  provider: string;
  account_id: string;
  metric_key: string;
  metric_name: string;
}

export interface IconRef {
  name: string;
  set: string;
  pack: string;
  version: string;
}

export interface Catalog {
  accounts: Account[];
  metrics: CatalogMetric[];
  exhausted_color: string;
  service_icons: Record<string, IconRef>;
  provider_icons: Record<string, IconRef>;
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

export interface NoteRange {
  service: string;
  account_id: string;
  text: string;
  start: string;
  end: string | null;
}

export interface Filters {
  services: string[];
  providers: string[];
  accounts: string[];
  metrics: string[];
}

export interface FunnelMetric {
  key: string;
  name: string;
}

export interface FunnelAccount {
  id: string;
  label: string;
  metrics: FunnelMetric[];
}

export interface FunnelProvider {
  provider: string;
  accounts: FunnelAccount[];
}

export interface FunnelBranch {
  service: string;
  providers: FunnelProvider[];
}

