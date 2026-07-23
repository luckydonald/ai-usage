import { describe, expect, it } from "vitest";

import { defaultFilters, toggleAccount, toggleMetric, toggleProvider, toggleService } from "./filterCascade";
import type { Filters, FunnelBranch } from "./types";

// codex -> app-server -> acct-codex -> five-hours
// claude -> web -> acct-web-a -> five-hours, seven-days
// claude -> web -> acct-web-b -> five-hours, seven-days
// claude -> statusline -> acct-statusline -> five-hours
const tree: FunnelBranch[] = [
  {
    service: "codex",
    providers: [{ provider: "app-server", accounts: [{ id: "acct-codex", label: "Codex", metrics: [{ key: "five-hours", name: "Five hours" }] }] }],
  },
  {
    service: "claude",
    providers: [
      {
        provider: "web",
        accounts: [
          { id: "acct-web-a", label: "Web A", metrics: [{ key: "five-hours", name: "Five hours" }, { key: "seven-days", name: "Seven days" }] },
          { id: "acct-web-b", label: "Web B", metrics: [{ key: "five-hours", name: "Five hours" }, { key: "seven-days", name: "Seven days" }] },
        ],
      },
      {
        provider: "statusline",
        accounts: [{ id: "acct-statusline", label: "Statusline", metrics: [{ key: "five-hours", name: "Five hours" }] }],
      },
    ],
  },
];

const empty: Filters = { services: [], providers: [], accounts: [], metrics: [] };

describe("defaultFilters", () => {
  it("populates every service/provider/account/metric_key from the tree", () => {
    const filters = defaultFilters(tree);
    expect(filters.services.sort()).toEqual(["claude", "codex"]);
    expect(filters.providers.sort()).toEqual(["app-server", "statusline", "web"]);
    expect(filters.accounts.sort()).toEqual(["acct-codex", "acct-statusline", "acct-web-a", "acct-web-b"]);
    expect(filters.metrics.sort()).toEqual(["five-hours", "seven-days"]);
  });
});

describe("toggleService (enable)", () => {
  it("force-enables every provider/account/metric reachable under the service, unconditionally", () => {
    const next = toggleService(tree, empty, "claude");
    expect(next.services).toEqual(["claude"]);
    expect(next.providers.sort()).toEqual(["statusline", "web"]);
    expect(next.accounts.sort()).toEqual(["acct-statusline", "acct-web-a", "acct-web-b"]);
    // Force-enables ALL metrics reachable, not just enough to display something.
    expect(next.metrics.sort()).toEqual(["five-hours", "seven-days"]);
  });
});

describe("toggleProvider (enable)", () => {
  it("ensures its service is active and enables all its accounts", () => {
    const next = toggleProvider(tree, empty, "web");
    expect(next.services).toEqual(["claude"]);
    expect(next.providers).toEqual(["web"]);
    expect(next.accounts.sort()).toEqual(["acct-web-a", "acct-web-b"]);
  });

  it("smart-enables an account's metrics only when it would otherwise show nothing", () => {
    const restricted: Filters = { ...empty, metrics: ["seven-days"] };
    const next = toggleProvider(tree, restricted, "app-server");
    // acct-codex only has "five-hours", which isn't in the restricted metrics list -> it would
    // show nothing, so its metrics get force-added.
    expect(next.metrics.sort()).toEqual(["five-hours", "seven-days"]);
  });

  it("leaves the metrics filter untouched when the account can already display something", () => {
    const restricted: Filters = { ...empty, metrics: ["seven-days"] };
    const next = toggleProvider(tree, restricted, "web");
    // acct-web-a/b already have "seven-days" active -> no need to add "five-hours" too.
    expect(next.metrics).toEqual(["seven-days"]);
  });
});

describe("toggleAccount (enable)", () => {
  it("ensures provider and service ancestors are active", () => {
    const next = toggleAccount(tree, empty, "acct-statusline");
    expect(next.services).toEqual(["claude"]);
    expect(next.providers).toEqual(["statusline"]);
    expect(next.accounts).toEqual(["acct-statusline"]);
  });

  it("applies the same smart metric rule as provider-level enable", () => {
    const restricted: Filters = { ...empty, metrics: ["seven-days"] };
    const next = toggleAccount(tree, restricted, "acct-statusline");
    expect(next.metrics.sort()).toEqual(["five-hours", "seven-days"]);
  });
});

describe("toggleMetric (enable)", () => {
  it("does nothing beyond adding the metric key when an already-active account already has it", () => {
    const active: Filters = { services: ["claude"], providers: ["web"], accounts: ["acct-web-a"], metrics: ["five-hours"] };
    const next = toggleMetric(tree, active, "seven-days");
    expect(next.accounts).toEqual(["acct-web-a"]);
    expect(next.providers).toEqual(["web"]);
    expect(next.services).toEqual(["claude"]);
    expect(next.metrics.sort()).toEqual(["five-hours", "seven-days"]);
  });

  it("unions in every account with that metric key plus their ancestors when nothing active supplies it", () => {
    const next = toggleMetric(tree, empty, "seven-days");
    expect(next.accounts.sort()).toEqual(["acct-web-a", "acct-web-b"]);
    expect(next.providers).toEqual(["web"]);
    expect(next.services).toEqual(["claude"]);
    // Does NOT pull in codex/statusline/acct-codex/acct-statusline — they don't have "seven-days".
    expect(next.accounts).not.toContain("acct-codex");
    expect(next.accounts).not.toContain("acct-statusline");
  });

  it("does not over-enable unrelated accounts when the metric is shared across services", () => {
    // "five-hours" is reachable from codex, web (x2), and statusline; with nothing active it
    // should pull in every one of them, since none is already displaying it.
    const next = toggleMetric(tree, empty, "five-hours");
    expect(next.accounts.sort()).toEqual(["acct-codex", "acct-statusline", "acct-web-a", "acct-web-b"]);
    expect(next.services.sort()).toEqual(["claude", "codex"]);
  });
});

describe("disable cascade", () => {
  it("reproduces the worked example: disabling the last active account orphans its provider and service, and any metric only it supplied", () => {
    const active: Filters = {
      services: ["claude"],
      providers: ["web"],
      accounts: ["acct-web-a"],
      metrics: ["five-hours", "seven-days"],
    };
    const next = toggleAccount(tree, active, "acct-web-a");
    expect(next.accounts).toEqual([]);
    expect(next.providers).toEqual([]); // "web" had only acct-web-a active -> orphaned
    expect(next.services).toEqual([]); // "claude" had only "web" active -> orphaned too
    expect(next.metrics).toEqual([]); // both metrics' only active account was acct-web-a
  });

  it("does not orphan a provider that still has another active account", () => {
    const active: Filters = {
      services: ["claude"],
      providers: ["web"],
      accounts: ["acct-web-a", "acct-web-b"],
      metrics: ["five-hours"],
    };
    const next = toggleAccount(tree, active, "acct-web-a");
    expect(next.providers).toEqual(["web"]);
    expect(next.services).toEqual(["claude"]);
    expect(next.accounts).toEqual(["acct-web-b"]);
  });

  it("does not orphan a metric shared across a different service while another connected account remains active", () => {
    const active: Filters = {
      services: ["claude", "codex"],
      providers: ["web", "app-server"],
      accounts: ["acct-web-a", "acct-codex"],
      metrics: ["five-hours"],
    };
    const next = toggleAccount(tree, active, "acct-web-a");
    // "five-hours" is still supplied by acct-codex, so it survives even though acct-web-a is gone.
    expect(next.metrics).toEqual(["five-hours"]);
    expect(next.accounts).toEqual(["acct-codex"]);
  });

  it("cascades left from the metric column: disabling an account's last active metric orphans the account, then its provider/service", () => {
    const active: Filters = {
      services: ["claude"],
      providers: ["statusline"],
      accounts: ["acct-statusline"],
      metrics: ["five-hours"],
    };
    const next = toggleMetric(tree, active, "five-hours");
    expect(next.metrics).toEqual([]);
    expect(next.accounts).toEqual([]); // acct-statusline had no metric left active
    expect(next.providers).toEqual([]); // statusline had no account left active
    expect(next.services).toEqual([]); // claude had no provider left active
  });
});
