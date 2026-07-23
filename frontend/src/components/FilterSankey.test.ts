import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

const chart = vi.hoisted(() => ({
  dispose: vi.fn(),
  on: vi.fn(),
  resize: vi.fn(),
  setOption: vi.fn(),
}));

vi.mock("echarts/core", () => ({
  init: vi.fn(() => chart),
  use: vi.fn(),
}));

import FilterSankey from "./FilterSankey.vue";
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

function mountSankey() {
  return mount(FilterSankey, {
    props: {
      tree,
      activeServices: [],
      activeProviders: [],
      activeAccounts: [],
      activeMetrics: [],
      dark: false,
    },
  });
}

afterEach(() => {
  vi.clearAllMocks();
});

function clickNode(kind: string, refId: string): void {
  const click = chart.on.mock.calls.find((call) => call[0] === "click")?.[1] as ((event: unknown) => void) | undefined;
  if (!click) throw new Error("chart click handler must be registered");
  click({ dataType: "node", data: { kind, refId } });
}

describe("FilterSankey", () => {
  it("passes deduped nodes/links for a metric shared across two accounts to setOption", () => {
    mountSankey();
    const option = chart.setOption.mock.calls[0]?.[0];
    const series = option.series[0];
    expect(series.type).toBe("sankey");
    const metricNodes = series.data.filter((node: { kind: string }) => node.kind === "metric");
    expect(metricNodes).toHaveLength(1);
    expect(series.links.filter((link: { target: string }) => link.target === metricNodes[0].name)).toHaveLength(2);
  });

  it("emits toggle-service when a service node is clicked", () => {
    const wrapper = mountSankey();
    clickNode("service", "claude");
    expect(wrapper.emitted("toggle-service")).toEqual([["claude"]]);
  });

  it("emits toggle-provider when a provider node is clicked", () => {
    const wrapper = mountSankey();
    clickNode("provider", "web");
    expect(wrapper.emitted("toggle-provider")).toEqual([["web"]]);
  });

  it("emits toggle-account when an account node is clicked", () => {
    const wrapper = mountSankey();
    clickNode("account", "acct-a");
    expect(wrapper.emitted("toggle-account")).toEqual([["acct-a"]]);
  });

  it("emits toggle-metric (once) when the shared metric node is clicked", () => {
    const wrapper = mountSankey();
    clickNode("metric", "five-hours");
    expect(wrapper.emitted("toggle-metric")).toEqual([["five-hours"]]);
  });

  it("ignores clicks on links (edges), not just nodes", () => {
    const wrapper = mountSankey();
    const click = chart.on.mock.calls.find((call) => call[0] === "click")?.[1] as (event: unknown) => void;
    click({ dataType: "edge", data: { kind: "metric", refId: "five-hours" } });
    expect(wrapper.emitted("toggle-metric")).toBeUndefined();
  });

  it("disposes the chart and removes the resize listener on unmount", () => {
    const wrapper = mountSankey();
    wrapper.unmount();
    expect(chart.dispose).toHaveBeenCalled();
  });
});
