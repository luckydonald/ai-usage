import { describe, expect, it } from "vitest";

import { defaultFilters, toggleAccount, toggleOrganization, toggleParser, toggleService } from "./filterCascade";
import type { Filters, SankeyService } from "./types";

const tree: SankeyService[] = [{
  service: "claude",
  accounts: [{
    id: "user@example.com",
    label: "user@example.com",
    organizations: [
      { id: "org-a", name: "Personal", parsers: [{ id: "web-a", provider: "web", label: "Web", metrics: [{ key: "five-hours", name: "Five hours" }] }] },
      { id: "org-b", name: "Work", parsers: [{ id: "web-b", provider: "web", label: "Web", metrics: [{ key: "five-hours", name: "Five hours" }] }] },
    ],
  }],
}];

const empty: Filters = { accounts: [], metrics: [] };

describe("account-aware filter selection", () => {
  it("defaults to every parser configuration and metric", () => {
    expect(defaultFilters(tree)).toEqual({ accounts: ["web-a", "web-b"], metrics: ["five-hours"] });
  });

  it("selects every descendant parser from service, account, and organization nodes", () => {
    expect(toggleService(empty, tree[0]!)).toEqual({ accounts: ["web-a", "web-b"], metrics: [] });
    expect(toggleAccount(empty, tree[0]!.accounts[0]!)).toEqual({ accounts: ["web-a", "web-b"], metrics: [] });
    expect(toggleOrganization(empty, tree[0]!.accounts[0]!.organizations[0]!)).toEqual({ accounts: ["web-a"], metrics: [] });
  });

  it("selects a parser node as one exact configuration", () => {
    expect(toggleParser(empty, tree[0]!.accounts[0]!.organizations[1]!.parsers[0]!)).toEqual({ accounts: ["web-b"], metrics: [] });
  });
});
