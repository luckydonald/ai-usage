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

  it("renders the active/inactive signal on the label chip, not the node bar", () => {
    // The node bar's own color depends on link partners too (see the link-opacity test below),
    // so it's an unreliable "is this node selected" signal on its own — the chip label carries
    // that signal instead, via its own solid background driven only by this node's active state.
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];

    const activeNode = buildSankeyData(tree, { ...noActive, services: ["codex"] }, false).nodes.find((node) => node.kind === "service");
    const inactiveNode = buildSankeyData(tree, noActive, false).nodes.find((node) => node.kind === "service");

    const chip = (node: typeof activeNode) => node?.label?.rich.name as { backgroundColor: string; color: string };
    expect(chip(activeNode).backgroundColor).toBe("#6c0de9");
    expect(chip(activeNode).color).toBe("#ffffff");
    expect(chip(inactiveNode).backgroundColor).toBe("#f4f2fb");
    expect(chip(inactiveNode).color).toBe("#16101f");

    // The node bar itself is the same low-key outline color regardless of active state.
    expect(activeNode?.itemStyle.color).toBe(inactiveNode?.itemStyle.color);
  });

  it("uses the dark-mode chip colors when `dark` is true", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const node = buildSankeyData(tree, { ...noActive, services: ["codex"] }, true).nodes.find((n) => n.kind === "service");
    const chip = node?.label?.rich.name as { backgroundColor: string };
    expect(node?.itemStyle.color).toBe("#241a3d");
    expect(chip.backgroundColor).toBe("#6c0de9");
  });

  it("only marks a link's color as active when both endpoints are active, but never fully transparent", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];

    const bothActive = buildSankeyData(tree, { ...noActive, services: ["codex"], providers: ["app-server"] }, false).links[0];
    const onlyOneActive = buildSankeyData(tree, { ...noActive, services: ["codex"] }, false).links[0];

    expect(bothActive?.lineStyle.opacity).toBe(0.5);
    expect(onlyOneActive?.lineStyle.opacity).toBe(0.15);
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

  it("still renders the label chip pill when a node has an icon", () => {
    const tree: FunnelBranch[] = [{ service: "codex", providers: [{ provider: "app-server", accounts: [] }] }];
    const icon = { name: "codex-icon", set: "brands", pack: "fontawesome-free-pack", version: "latest" };

    const { nodes } = buildSankeyData(tree, { ...noActive, services: ["codex"] }, false, { codex: icon }, {});
    const chip = nodes.find((node) => node.kind === "service")?.label?.rich.name as { backgroundColor: string };
    expect(chip.backgroundColor).toBe("#6c0de9");
  });
});
