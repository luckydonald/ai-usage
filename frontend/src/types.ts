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
  account: AccountHierarchy;
  parser_label: string;
}

export interface Organization {
  id: string;
  name: string | null;
}

export interface AccountHierarchy {
  login: string | null;
  organization: Organization | null;
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
  metric_icons: Record<string, IconRef>;
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
  accounts: string[];
  metrics: string[];
}

export interface SankeyMetric {
  key: string;
  name: string;
  icon?: IconRef;
}

export interface SankeyParser {
  id: string;
  provider: string;
  label: string;
  icon?: IconRef;
  metrics: SankeyMetric[];
}

export interface SankeyOrganization {
  id: string | null;
  name: string | null;
  parsers: SankeyParser[];
}

export interface SankeyAccount {
  id: string;
  label: string;
  organizations: SankeyOrganization[];
}

export interface SankeyService {
  service: string;
  accounts: SankeyAccount[];
}
