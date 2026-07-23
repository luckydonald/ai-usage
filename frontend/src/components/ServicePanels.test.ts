import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { GraphSeries } from "../types";
import RelativeTime from "./RelativeTime.vue";
import ServicePanels from "./ServicePanels.vue";

const series: GraphSeries[] = [
  {
    service: "codex",
    provider: "app-server",
    account_id: "account",
    metric_key: "five-hours",
    metric_name: "Five hours",
    color: "#f97316",
    points: [{ at: "2026-07-17T10:00:00Z", percentage: 40, current: null, maximum: null }],
    windows: [
      {
        start: "2026-07-17T09:00:00Z",
        end: "2026-07-17T14:00:00Z",
        maximum_percentage: 40,
        exhausted_from: null,
        current: true,
        projected_end_percentage: 90,
      },
    ],
  },
];

describe("ServicePanels", () => {
  it("renders no panels when there is no series data", () => {
    const wrapper = mount(ServicePanels, { props: { series: [], accountLabels: {}, parserLabels: {} } });
    expect(wrapper.find(".info-panels").exists()).toBe(false);
  });

  it("renders the window's start/end as relative-time components with the absolute time as a tooltip", () => {
    const wrapper = mount(ServicePanels, { props: { series, accountLabels: { account: "person@example.com" }, parserLabels: { account: "Web" } } });

    const relativeTimes = wrapper.findAllComponents(RelativeTime);
    expect(relativeTimes.length).toBe(2);

    expect(wrapper.text()).toContain("person@example.com");
    expect(wrapper.text()).toContain("Peak usage: 40.0%");
    expect(wrapper.text()).toContain("Projected to land at 90.0%");
    expect(wrapper.text()).toContain("10.0% of your limit would be left to use");

    const start = new Date("2026-07-17T09:00:00Z");
    expect(wrapper.html()).toContain(`title="${start.toLocaleString()}"`);
  });

  it("shows a placeholder when a metric has no window data", () => {
    const noWindowSeries: GraphSeries[] = [{ ...series[0]!, windows: [] }];
    const wrapper = mount(ServicePanels, { props: { series: noWindowSeries, accountLabels: {}, parserLabels: {} } });
    expect(wrapper.text()).toContain("No window data yet.");
  });
});
