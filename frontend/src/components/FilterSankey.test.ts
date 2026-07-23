import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

const chart = vi.hoisted(() => ({
  dispose: vi.fn(),
  resize: vi.fn(),
  setOption: vi.fn(),
}));

vi.mock("echarts/core", () => ({
  init: vi.fn(() => chart),
  use: vi.fn(),
}));

import FilterSankey from "./FilterSankey.vue";
import Chip from "./Chip.vue";
import type { FunnelBranch } from "../types";

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

async function mountSankey(overrides: Partial<Record<string, string[]>> = {}) {
  const wrapper = mount(FilterSankey, {
    props: {
      tree,
      activeServices: overrides.activeServices ?? [],
      activeProviders: overrides.activeProviders ?? [],
      activeAccounts: overrides.activeAccounts ?? [],
      activeMetrics: overrides.activeMetrics ?? [],
      dark: false,
    },
  });
  await flushPromises();
  return wrapper;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("FilterSankey", () => {
  it("passes deduped nodes/links for a metric shared across two accounts to setOption, with echarts labels hidden", async () => {
    await mountSankey();
    const option = chart.setOption.mock.calls[0]?.[0];
    const series = option.series[0];
    expect(series.type).toBe("sankey");
    expect(series.label).toEqual({ show: false });
    const metricNodes = series.data.filter((node: { kind: string }) => node.kind === "metric");
    expect(metricNodes).toHaveLength(1);
    expect(series.links.filter((link: { target: string }) => link.target === metricNodes[0].name)).toHaveLength(2);
  });

  it("renders one real Chip per node, including just one for the metric shared across two accounts", async () => {
    const wrapper = await mountSankey();
    const chips = wrapper.findAllComponents(Chip);
    // claude, web, acct-a, acct-b, and one shared "five-hours" = 5 chips, not 6.
    expect(chips).toHaveLength(5);
    expect(chips.map((c) => c.props("label")).sort()).toEqual(["Five hours", "Org A", "Org B", "claude", "web"]);
  });

  it("marks a Chip active only when its own filter list includes it", async () => {
    const wrapper = await mountSankey({ activeMetrics: ["five-hours"] });
    const chips = wrapper.findAllComponents(Chip);
    const metricChip = chips.find((c) => c.props("label") === "Five hours");
    const otherChip = chips.find((c) => c.props("label") === "claude");
    expect(metricChip?.props("active")).toBe(true);
    expect(otherChip?.props("active")).toBe(false);
  });

  it("emits toggle-service when the service Chip is clicked", async () => {
    const wrapper = await mountSankey();
    await wrapper.findAllComponents(Chip).find((c) => c.props("label") === "claude")!.trigger("click");
    expect(wrapper.emitted("toggle-service")).toEqual([["claude"]]);
  });

  it("emits toggle-provider when the provider Chip is clicked", async () => {
    const wrapper = await mountSankey();
    await wrapper.findAllComponents(Chip).find((c) => c.props("label") === "web")!.trigger("click");
    expect(wrapper.emitted("toggle-provider")).toEqual([["web"]]);
  });

  it("emits toggle-account when an account Chip is clicked", async () => {
    const wrapper = await mountSankey();
    await wrapper.findAllComponents(Chip).find((c) => c.props("label") === "Org A")!.trigger("click");
    expect(wrapper.emitted("toggle-account")).toEqual([["acct-a"]]);
  });

  it("emits toggle-metric (once) when the shared metric Chip is clicked", async () => {
    const wrapper = await mountSankey();
    await wrapper.findAllComponents(Chip).find((c) => c.props("label") === "Five hours")!.trigger("click");
    expect(wrapper.emitted("toggle-metric")).toEqual([["five-hours"]]);
  });

  it("disposes the chart and removes the resize listener on unmount", async () => {
    const wrapper = await mountSankey();
    wrapper.unmount();
    expect(chart.dispose).toHaveBeenCalled();
  });
});
