import type { Catalog, Filters, GraphSeries, LatestMetric, NoteRange } from "./types";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`API request failed with HTTP ${response.status}`);
  return (await response.json()) as T;
}

export function fetchCatalog(): Promise<Catalog> {
  return request<Catalog>("/api/v1/catalog");
}

export function fetchLatest(): Promise<LatestMetric[]> {
  return request<LatestMetric[]>("/api/v1/latest");
}

export function fetchSeries(start: Date, end: Date, filters: Filters): Promise<GraphSeries[]> {
  const parameters = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
  for (const value of filters.accounts) parameters.append("account", value);
  for (const value of filters.metrics) parameters.append("metric", value);
  return request<GraphSeries[]>(`/api/v1/series?${parameters.toString()}`);
}

export function fetchLegacySeries(start: Date, end: Date, filters: Filters): Promise<GraphSeries[]> {
  const parameters = new URLSearchParams({ start: start.toISOString(), end: end.toISOString(), aggregation: "legacy" });
  for (const value of filters.accounts) parameters.append("account", value);
  for (const value of filters.metrics) parameters.append("metric", value);
  return request<GraphSeries[]>(`/api/v1/series?${parameters.toString()}`);
}

export function fetchNotes(): Promise<NoteRange[]> {
  return request<NoteRange[]>("/api/v1/notes");
}
