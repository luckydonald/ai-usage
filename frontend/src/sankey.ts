import type { IconRef, SankeyService } from "./types";

export type NodeKind = "service" | "account" | "organization" | "parser" | "metric";

export interface SankeyNodeDatum {
  name: string;
  kind: NodeKind;
  refId: string;
  displayName: string;
  title?: string;
  icon?: IconRef;
  active: boolean;
  itemStyle: { color: string; borderColor: string; borderWidth: number };
  label: { show: false };
}

export interface SankeyLinkDatum {
  source: string;
  target: string;
  value: number;
  lineStyle: { color: string; opacity: number };
}

export interface SankeyData {
  nodes: SankeyNodeDatum[];
  links: SankeyLinkDatum[];
}

const ACTIVE_COLOR = "#6c0de9";
const INACTIVE_COLOR = { light: "#f4f2fb", dark: "#241a3d" };
const BORDER_COLOR = { light: "#ded9f0", dark: "#3a2c5c" };

function nodeStyle(dark: boolean): SankeyNodeDatum["itemStyle"] {
  return { color: dark ? INACTIVE_COLOR.dark : INACTIVE_COLOR.light, borderColor: dark ? BORDER_COLOR.dark : BORDER_COLOR.light, borderWidth: 1 };
}

function linkStyle(active: boolean, dark: boolean): SankeyLinkDatum["lineStyle"] {
  return { color: active ? ACTIVE_COLOR : dark ? BORDER_COLOR.dark : BORDER_COLOR.light, opacity: active ? 0.5 : 0.35 };
}

export function buildSankeyData(
  tree: SankeyService[],
  activeAccounts: string[],
  activeMetrics: string[],
  dark: boolean,
  serviceIcons: Record<string, IconRef> = {},
  metricIcons: Record<string, IconRef> = {},
): SankeyData {
  const nodes = new Map<string, SankeyNodeDatum>();
  const links: SankeyLinkDatum[] = [];
  const addNode = (id: string, displayName: string, kind: NodeKind, refId: string, active: boolean, icon?: IconRef, title?: string): void => {
    if (!nodes.has(id)) nodes.set(id, { name: id, kind, refId, displayName, title, icon, active, itemStyle: nodeStyle(dark), label: { show: false } });
  };
  const addLink = (source: string, target: string, active: boolean): void => {
    links.push({ source, target, value: 1, lineStyle: linkStyle(active, dark) });
  };

  for (const service of tree) {
    const serviceId = `service:${service.service}`;
    const serviceActive = service.accounts.some((account) => account.organizations.some((organization) => organization.parsers.some((parser) => activeAccounts.includes(parser.id))));
    addNode(serviceId, service.service, "service", service.service, serviceActive, serviceIcons[service.service], service.service);
    for (const account of service.accounts) {
      const accountId = `account:${service.service}:${account.id}`;
      const accountActive = account.organizations.some((organization) => organization.parsers.some((parser) => activeAccounts.includes(parser.id)));
      addNode(accountId, account.label, "account", account.id, accountActive);
      addLink(serviceId, accountId, accountActive);
      for (const organization of account.organizations) {
        const hasVisibleOrganization = organization.name !== null;
        const organizationId = `organization:${service.service}:${account.id}:${organization.id ?? "none"}`;
        const organizationActive = organization.parsers.some((parser) => activeAccounts.includes(parser.id));
        if (hasVisibleOrganization) addNode(organizationId, organization.name!, "organization", organization.id!, organizationActive, undefined, organization.id!);
        if (hasVisibleOrganization) addLink(accountId, organizationId, organizationActive);
        const parentId = hasVisibleOrganization ? organizationId : accountId;
        for (const parser of organization.parsers) {
          const parserId = `parser:${parser.id}`;
          const parserActive = activeAccounts.includes(parser.id);
          addNode(parserId, parser.label, "parser", parser.id, parserActive, parser.icon, `Configuration ${parser.id}`);
          addLink(parentId, parserId, parserActive);
          for (const metric of parser.metrics) {
            const metricId = `metric:${metric.key}`;
            const metricActive = activeMetrics.includes(metric.key);
            addNode(metricId, metric.name, "metric", metric.key, metricActive, metric.icon ?? metricIcons[metric.key]);
            addLink(parserId, metricId, parserActive && metricActive);
          }
        }
      }
    }
  }
  return { nodes: [...nodes.values()], links };
}
