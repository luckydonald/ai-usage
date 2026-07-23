import type { FunnelBranch, IconRef } from "./types";

export type NodeKind = "service" | "provider" | "account" | "metric";

// The node's visual/interactive representation (icon, label, active/inactive color, click
// target) is a real `Chip.vue` overlaid in `FilterSankey.vue` on top of the node's rendered
// position — not drawn by echarts itself. echarts rich-text labels can't combine a solid
// pill background with an image icon in the same token, so a genuine "icon inside the button"
// look (matching the old chip-tree component) needs a real DOM element, not a canvas label.
export interface SankeyNodeDatum {
  name: string;
  kind: NodeKind;
  refId: string;
  displayName: string;
  icon?: IconRef;
  itemStyle: { color: string; borderColor: string; borderWidth: number };
  label: { show: false };
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

// Mirrors `--color-primary` / `--surface-muted` / `--border` in `styles/main.scss` — kept as
// explicit hex here (not a CSS var) since these values feed an echarts option object, not a
// stylesheet. Only used for the link ribbons and the node bars' low-key outline now; the actual
// active/inactive chip coloring lives in `Chip.vue`'s own styles via the overlay.
const ACTIVE_COLOR = "#6c0de9";
const INACTIVE_COLOR = { light: "#f4f2fb", dark: "#241a3d" };
const BORDER_COLOR = { light: "#ded9f0", dark: "#3a2c5c" };

// The node bar itself is just a low-key, always-visible anchor for its links — the overlaid
// `Chip` carries the actual active/inactive signal and the icon, so the bar doesn't need to.
function nodeStyle(dark: boolean): { color: string; borderColor: string; borderWidth: number } {
  return { color: dark ? INACTIVE_COLOR.dark : INACTIVE_COLOR.light, borderColor: dark ? BORDER_COLOR.dark : BORDER_COLOR.light, borderWidth: 1 };
}

function linkStyle(active: boolean, dark: boolean): SankeyLinkDatum["lineStyle"] {
  return { color: active ? ACTIVE_COLOR : dark ? INACTIVE_COLOR.dark : INACTIVE_COLOR.light, opacity: active ? 0.5 : 0.15 };
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
  // (unique) node id, and the human-readable text is drawn by the `Chip` overlay instead of an
  // echarts label (see `SankeyNodeDatum`'s doc comment for why).
  function addNode(id: string, displayName: string, kind: NodeKind, refId: string, icon: IconRef | undefined): void {
    if (nodes.has(id)) return;
    nodes.set(id, { name: id, kind, refId, displayName, icon, itemStyle: nodeStyle(dark), label: { show: false } });
  }

  function addLink(sourceId: string, targetId: string, isActive: boolean): void {
    links.push({ source: sourceId, target: targetId, value: 1, lineStyle: linkStyle(isActive, dark) });
  }

  for (const branch of tree) {
    const serviceId = `service:${branch.service}`;
    const serviceActive = active.services.includes(branch.service);
    addNode(serviceId, branch.service, "service", branch.service, serviceIcons[branch.service]);

    for (const providerNode of branch.providers) {
      const providerId = `provider:${branch.service}:${providerNode.provider}`;
      const providerActive = active.providers.includes(providerNode.provider);
      addNode(providerId, providerNode.provider, "provider", providerNode.provider, providerIcons[providerNode.provider]);
      addLink(serviceId, providerId, serviceActive && providerActive);

      for (const accountNode of providerNode.accounts) {
        const accountId = `account:${accountNode.id}`;
        const accountActive = active.accounts.includes(accountNode.id);
        addNode(accountId, accountNode.label, "account", accountNode.id, undefined);
        addLink(providerId, accountId, providerActive && accountActive);

        for (const metric of accountNode.metrics) {
          const metricId = `metric:${metric.key}`;
          const metricActive = active.metrics.includes(metric.key);
          addNode(metricId, metric.name, "metric", metric.key, undefined);
          addLink(accountId, metricId, accountActive && metricActive);
        }
      }
    }
  }

  return { nodes: [...nodes.values()], links };
}
