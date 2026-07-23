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

  it("colors a node active only when its own filter list includes it", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];

    const activeNode = buildSankeyData(tree, { ...noActive, services: ["codex"] }, false).nodes.find((node) => node.kind === "service");
    const inactiveNode = buildSankeyData(tree, noActive, false).nodes.find((node) => node.kind === "service");

    expect(activeNode?.itemStyle.color).toBe("#6c0de9");
    expect(inactiveNode?.itemStyle.color).toBe("#f4f2fb");
  });

  it("uses the dark-mode inactive color when `dark` is true", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const node = buildSankeyData(tree, noActive, true).nodes.find((n) => n.kind === "service");
    expect(node?.itemStyle.color).toBe("#241a3d");
  });

  it("only marks a link active when both endpoints are active", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];

    const bothActive = buildSankeyData(tree, { ...noActive, services: ["codex"], providers: ["app-server"] }, false).links[0];
    const onlyOneActive = buildSankeyData(tree, { ...noActive, services: ["codex"] }, false).links[0];

    expect(bothActive?.lineStyle.opacity).toBe(0.6);
    expect(onlyOneActive?.lineStyle.opacity).toBe(0.3);
  });

  it("attaches a resolved icon URL for a service/provider that has one in the catalog", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const icon = { name: "codex-icon", set: "brands", pack: "fontawesome-free-pack", version: "latest" };

    const { nodes } = buildSankeyData(tree, noActive, false, { codex: icon }, {});
    const serviceNode = nodes.find((node) => node.kind === "service");

    expect(serviceNode?.label?.formatter).toContain("{icon|}");
    expect((serviceNode?.label?.rich.icon as { backgroundColor: { image: string } }).backgroundColor.image).toBe(
      "/img/icons/fontawesome-free-pack/latest/brands/codex-icon.svg",
    );
  });
});
