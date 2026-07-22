import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import FilterFunnel from "./FilterFunnel.vue";
import type { FunnelBranch } from "../types";

const tree: FunnelBranch[] = [
  {
    service: "claude",
    providers: [
      {
        provider: "web",
        accounts: [
          {
            id: "account-1",
            label: "Claude private web API (person@example.com's Organization)",
            metrics: [
              { key: "five-hours", name: "Five hours" },
              { key: "seven-days", name: "Seven days" },
            ],
          },
        ],
      },
      { provider: "statusline", accounts: [] },
      { provider: "usage-cli", accounts: [] },
    ],
  },
  { service: "codex", providers: [{ provider: "app-server", accounts: [] }] },
];

describe("FilterFunnel", () => {
  it("renders one branch per service, nesting providers, accounts, and metrics underneath", () => {
    const wrapper = mount(FilterFunnel, {
      props: { tree, activeServices: [], activeProviders: [], activeAccounts: [], activeMetrics: [] },
    });
    const branches = wrapper.findAll(".funnel-branch");
    // 2 services + 4 providers + 1 account = 7 branch rows.
    expect(branches).toHaveLength(7);
    const text = wrapper.text();
    expect(text).toContain("claude");
    expect(text).toContain("web");
    expect(text).toContain("statusline");
    expect(text).toContain("usage-cli");
    expect(text).toContain("Claude private web API (person@example.com's Organization)");
    expect(text).toContain("Five hours");
    expect(text).toContain("Seven days");
    expect(text).toContain("codex");
    expect(text).toContain("app-server");
  });

  it("marks the selected chip at every level as active", () => {
    const wrapper = mount(FilterFunnel, {
      props: {
        tree,
        activeServices: ["codex"],
        activeProviders: ["web"],
        activeAccounts: ["account-1"],
        activeMetrics: ["seven-days"],
      },
    });
    const chip = (label: string) => wrapper.findAll(".chip").find((candidate) => candidate.text() === label);
    expect(chip("codex")?.classes()).toContain("active");
    expect(chip("web")?.classes()).toContain("active");
    expect(chip("Claude private web API (person@example.com's Organization)")?.classes()).toContain("active");
    expect(chip("Seven days")?.classes()).toContain("active");
    expect(chip("statusline")?.classes()).not.toContain("active");
    expect(chip("Five hours")?.classes()).not.toContain("active");
  });

  it("emits a toggle event for the level whose chip was clicked", async () => {
    const wrapper = mount(FilterFunnel, {
      props: { tree, activeServices: [], activeProviders: [], activeAccounts: [], activeMetrics: [] },
    });
    const chip = (label: string) => wrapper.findAll(".chip").find((candidate) => candidate.text() === label)!;
    await chip("codex").trigger("click");
    await chip("app-server").trigger("click");
    await chip("Claude private web API (person@example.com's Organization)").trigger("click");
    await chip("Five hours").trigger("click");
    expect(wrapper.emitted("toggle-service")).toEqual([["codex"]]);
    expect(wrapper.emitted("toggle-provider")).toEqual([["app-server"]]);
    expect(wrapper.emitted("toggle-account")).toEqual([["account-1"]]);
    expect(wrapper.emitted("toggle-metric")).toEqual([["five-hours"]]);
  });
});
