import { describe, expect, it } from "vitest";

import { buildSankeyData } from "./sankey";
import type { FunnelBranch } from "./types";

const noActive = { services: [], providers: [], accounts: [], metrics: [] };

describe("buildSankeyData", () => {
  it("returns no nodes or links for an empty tree", () => {
    expect(buildSankeyData([], noActive, false)).toEqual({ nodes: [], links: [] });
  });

  it("converges a metric_key shared by two accounts into a single node with two incoming links", () => {
    const tree: FunnelBranch[] = [
      {
        service: "claude",
        providers: [
          {
            provider: "web",
            accounts: [
              { id: "acct-a", label: "Org A", metrics: [{ key: "five-hours", name: "Five hours" }] },
              { id: "acct-b", label: "Org B", metrics: [{ key: "five-hours", name: "Five hours" }] },
            ],
          },
        ],
      },
    ];

    const { nodes, links } = buildSankeyData(tree, noActive, false);

    const metricNodes = nodes.filter((node) => node.kind === "metric");
    expect(metricNodes).toHaveLength(1);
    expect(metricNodes[0]?.refId).toBe("five-hours");
    expect(metricNodes[0]?.displayName).toBe("Five hours");

    const metricLinks = links.filter((link) => link.target === metricNodes[0]?.name);
    expect(metricLinks).toHaveLength(2);
    expect(metricLinks.map((link) => link.source).sort()).toEqual(["account:acct-a", "account:acct-b"]);
  });

  it("keeps distinct nodes for every service/provider/account level", () => {
    const tree: FunnelBranch[] = [
      { service: "codex", providers: [{ provider: "app-server", accounts: [{ id: "acct-codex", label: "Codex", metrics: [{ key: "five-hours", name: "Five hours" }] }] }] },
      { service: "claude", providers: [{ provider: "web", accounts: [{ id: "acct-web", label: "Web", metrics: [{ key: "five-hours", name: "Five hours" }] }] }] },
    ];

    const { nodes, links } = buildSankeyData(tree, noActive, false);

    expect(nodes.filter((node) => node.kind === "service").map((node) => node.refId).sort()).toEqual(["claude", "codex"]);
    expect(nodes.filter((node) => node.kind === "provider").map((node) => node.refId).sort()).toEqual(["app-server", "web"]);
    expect(nodes.filter((node) => node.kind === "account").map((node) => node.refId).sort()).toEqual(["acct-codex", "acct-web"]);
    // Both services happen to share a "five-hours" metric_key; still just one shared node.
    expect(nodes.filter((node) => node.kind === "metric")).toHaveLength(1);
    expect(links).toHaveLength(6);
  });

  it("never shows echarts' own node label (the Chip overlay draws the text/icon instead)", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const node = buildSankeyData(tree, noActive, false).nodes.find((n) => n.kind === "service");
    expect(node?.label).toEqual({ show: false });
  });

  it("uses the same low-key node bar style regardless of dark mode's role vs. active state", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const light = buildSankeyData(tree, noActive, false).nodes.find((n) => n.kind === "service");
    const dark = buildSankeyData(tree, noActive, true).nodes.find((n) => n.kind === "service");
    expect(light?.itemStyle.color).toBe("#f4f2fb");
    expect(dark?.itemStyle.color).toBe("#241a3d");
  });

  it("only marks a link's color as active when both endpoints are active, but never fully transparent", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];

    const bothActive = buildSankeyData(tree, { ...noActive, services: ["codex"], providers: ["app-server"] }, false).links[0];
    const onlyOneActive = buildSankeyData(tree, { ...noActive, services: ["codex"] }, false).links[0];

    expect(bothActive?.lineStyle.opacity).toBe(0.5);
    expect(onlyOneActive?.lineStyle.opacity).toBe(0.35);
  });

  it("attaches the raw icon ref for a service/provider that has one in the catalog, for the overlay to resolve", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const icon = { name: "codex-icon", set: "brands", pack: "fontawesome-free-pack", version: "latest" };

    const { nodes } = buildSankeyData(tree, noActive, false, { codex: icon }, {});
    const serviceNode = nodes.find((node) => node.kind === "service");
    const providerNode = nodes.find((node) => node.kind === "provider");
    const accountAndMetricNodes = nodes.filter((node) => node.kind === "account" || node.kind === "metric");

    expect(serviceNode?.icon).toEqual(icon);
    expect(providerNode?.icon).toBeUndefined();
    expect(accountAndMetricNodes.every((node) => node.icon === undefined)).toBe(true);
  });
});
