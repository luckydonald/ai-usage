import { describe, expect, it } from "vitest";

import { buildSankeyData } from "./sankey";
import type { SankeyService } from "./types";

const tree: SankeyService[] = [{
  service: "claude",
  accounts: [{
    id: "user@example.com",
    label: "user@example.com",
    organizations: [{
      id: "org-a",
      name: "Work",
      parsers: [{ id: "config-a", provider: "web", label: "Web", metrics: [{ key: "five-hours", name: "Five hours" }] }],
    }],
  }],
}];

describe("buildSankeyData", () => {
  it("renders account, organization, and parser nodes while retaining config identity in the parser", () => {
    const { nodes, links } = buildSankeyData(tree, ["config-a"], ["five-hours"], false);
    expect(nodes.map((node) => node.kind)).toEqual(["service", "account", "organization", "parser", "metric"]);
    const parser = nodes.find((node) => node.kind === "parser");
    expect(parser).toMatchObject({ displayName: "Web", refId: "config-a", title: "Configuration config-a" });
    expect(links).toHaveLength(4);
  });

  it("hides an unnamed organization node while keeping its parser reachable", () => {
    const unnamed: SankeyService[] = [{ ...tree[0]!, accounts: [{ ...tree[0]!.accounts[0]!, organizations: [{ id: "org-a", name: null, parsers: tree[0]!.accounts[0]!.organizations[0]!.parsers }] }] }];
    expect(buildSankeyData(unnamed, [], [], false).nodes.map((node) => node.kind)).toEqual(["service", "account", "parser", "metric"]);
  });
});
