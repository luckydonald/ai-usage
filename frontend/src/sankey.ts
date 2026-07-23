import type { FunnelBranch, IconRef } from "./types";

export type NodeKind = "service" | "provider" | "account" | "metric";

export interface SankeyNodeDatum {
  name: string;
  kind: NodeKind;
  refId: string;
  itemStyle: { color: string };
  label?: { formatter: string; rich: Record<string, unknown> };
}

export interface SankeyLinkDatum {
  source: string;
  target: string;
  value: number;
  lineStyle: { color: string; opacity: number };
}

export interface ActiveFilters {
  services: string[];
  providers: string[];
  accounts: string[];
  metrics: string[];
}

export interface SankeyData {
  nodes: SankeyNodeDatum[];
  links: SankeyLinkDatum[];
}

const ACTIVE_TEXT_COLOR = "#ffffff";
// Mirrors `--color-primary` / `--surface-muted` / `--text` in `styles/main.scss`, and the
// `.chip`/`.chip.active` rule built on top of them — kept as explicit hex here (not a CSS var)
// since these values feed an echarts option object, not a stylesheet.
const ACTIVE_COLOR = "#6c0de9";
const INACTIVE_COLOR = { light: "#f4f2fb", dark: "#241a3d" };
const INACTIVE_TEXT_COLOR = { light: "#16101f", dark: "#f1edfb" };

function iconUrl(icon: IconRef): string {
  return `/img/icons/${icon.pack}/${icon.version}/${icon.set}/${icon.name}.svg`;
}

function nodeStyle(active: boolean, dark: boolean): { color: string } {
  return { color: active ? ACTIVE_COLOR : dark ? INACTIVE_COLOR.dark : INACTIVE_COLOR.light };
}

function labelFor(name: string, active: boolean, dark: boolean, icon: IconRef | undefined): SankeyNodeDatum["label"] {
  const textColor = active ? ACTIVE_TEXT_COLOR : dark ? INACTIVE_TEXT_COLOR.dark : INACTIVE_TEXT_COLOR.light;
  if (!icon) {
    return { formatter: `{name|${name}}`, rich: { name: { color: textColor } } };
  }
  return {
    formatter: `{icon|} {name|${name}}`,
    rich: {
      icon: { height: 16, width: 16, backgroundColor: { image: iconUrl(icon) } },
      name: { color: textColor },
    },
  };
}

function linkStyle(active: boolean, dark: boolean): SankeyLinkDatum["lineStyle"] {
  return { color: active ? ACTIVE_COLOR : dark ? INACTIVE_COLOR.dark : INACTIVE_COLOR.light, opacity: active ? 0.6 : 0.3 };
}

// Builds echarts Sankey `nodes`/`links` from the service -> provider -> account -> metric tree.
// Metric nodes are deduped globally by `metric_key` (not per-account/provider) since the actual
// filter model (`Filters.metrics`) treats `metric_key` as a global identity already — this is
// what makes a metric shared by two accounts converge into one node with two incoming links,
// instead of rendering as a duplicate leaf per account like the old chip tree did.
export function buildSankeyData(
  tree: FunnelBranch[],
  active: ActiveFilters,
  dark: boolean,
  serviceIcons: Record<string, IconRef> = {},
  providerIcons: Record<string, IconRef> = {},
): SankeyData {
  const nodes = new Map<string, SankeyNodeDatum>();
  const links: SankeyLinkDatum[] = [];

  // Sankey identifies/links nodes by `name`, which must be unique — so `name` holds the
  // (unique) node id, and the human-readable text is drawn separately via a custom `label`
  // formatter instead of relying on echarts' default (which would just print `name`, i.e. the id).
  function addNode(id: string, displayName: string, kind: NodeKind, refId: string, isActive: boolean, icon: IconRef | undefined): void {
    if (nodes.has(id)) return;
    nodes.set(id, { name: id, kind, refId, itemStyle: nodeStyle(isActive, dark), label: labelFor(displayName, isActive, dark, icon) });
  }

  function addLink(sourceId: string, targetId: string, isActive: boolean): void {
    links.push({ source: sourceId, target: targetId, value: 1, lineStyle: linkStyle(isActive, dark) });
  }

  for (const branch of tree) {
    const serviceId = `service:${branch.service}`;
    const serviceActive = active.services.includes(branch.service);
    addNode(serviceId, branch.service, "service", branch.service, serviceActive, serviceIcons[branch.service]);

    for (const providerNode of branch.providers) {
      const providerId = `provider:${branch.service}:${providerNode.provider}`;
      const providerActive = active.providers.includes(providerNode.provider);
      addNode(providerId, providerNode.provider, "provider", providerNode.provider, providerActive, providerIcons[providerNode.provider]);
      addLink(serviceId, providerId, serviceActive && providerActive);

      for (const accountNode of providerNode.accounts) {
        const accountId = `account:${accountNode.id}`;
        const accountActive = active.accounts.includes(accountNode.id);
        addNode(accountId, accountNode.label, "account", accountNode.id, accountActive, undefined);
        addLink(providerId, accountId, providerActive && accountActive);

        for (const metric of accountNode.metrics) {
          const metricId = `metric:${metric.key}`;
          const metricActive = active.metrics.includes(metric.key);
          addNode(metricId, metric.name, "metric", metric.key, metricActive, undefined);
          addLink(accountId, metricId, accountActive && metricActive);
        }
      }
    }
  }

  return { nodes: [...nodes.values()], links };
}
