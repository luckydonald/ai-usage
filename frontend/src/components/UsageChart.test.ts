import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GraphSeries } from "../types";

type Handler = (raw: unknown) => void;

const handlers: Record<string, Handler> = {};
const zrHandlers: Record<string, Handler> = {};
let setOptionCalls = 0;

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: vi.fn(() => ({
    setOption: vi.fn(() => {
      setOptionCalls += 1;
    }),
    on: vi.fn((event: string, filterOrHandler: unknown, maybeHandler?: Handler) => {
      const handler = typeof maybeHandler === "function" ? maybeHandler : (filterOrHandler as Handler);
      const filter = typeof maybeHandler === "function" ? (filterOrHandler as { componentType?: string }) : undefined;
      handlers[filter?.componentType ? `${event}:${filter.componentType}` : event] = handler;
    }),
    getZr: vi.fn(() => ({
      on: vi.fn((event: string, handler: Handler) => {
        zrHandlers[event] = handler;
      }),
    })),
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
}));
vi.mock("echarts/charts", () => ({ LineChart: {} }));
vi.mock("echarts/components", () => ({
  GridComponent: {},
  LegendComponent: {},
  LegendScrollComponent: {},
  MarkAreaComponent: {},
  MarkLineComponent: {},
  TooltipComponent: {},
}));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

const series: GraphSeries = {
  service: "codex",
  provider: "app-server",
  account_id: "account",
  metric_key: "five-hours",
  metric_name: "Five hours",
  color: "#f97316",
  points: [{ at: "2026-07-17T10:00:00Z", percentage: 20, current: null, maximum: null }],
  windows: [{
    start: "2026-07-17T09:00:00Z",
    end: "2026-07-17T14:00:00Z",
    maximum_percentage: 40,
    exhausted_from: null,
    current: true,
    projected_end_percentage: 90,
  }],
};

async function mountChart() {
  const { default: UsageChart } = await import("./UsageChart.vue");
  return mount(UsageChart, {
    props: {
      series: [series],
      dark: false,
      exhaustedColor: "#6b7280",
      hiddenSeriesKeys: [],
      rangeStart: new Date("2026-07-17T00:00:00Z"),
      rangeEnd: new Date("2026-07-18T00:00:00Z"),
      accountLabels: {},
      notes: [],
      showDataPoints: false,
    },
  });
}

beforeEach(() => {
  setOptionCalls = 0;
  for (const key of Object.keys(handlers)) delete handlers[key];
  for (const key of Object.keys(zrHandlers)) delete zrHandlers[key];
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("UsageChart markArea region tooltip", () => {
  it("renders the region tooltip and hides the built-in tooltip via CSS when hovering a window's markArea", async () => {
    const wrapper = await mountChart();
    expect(wrapper.get(".usage-chart-wrap").classes()).not.toContain("hiding-native-tooltip");

    handlers["mouseover:markArea"]!({
      seriesName: "Five hours · app-server · account",
      data: { windowIndex: 0 },
      event: { offsetX: 42, offsetY: 24 },
    });
    await wrapper.vm.$nextTick();

    expect(wrapper.get(".usage-chart-wrap").classes()).toContain("hiding-native-tooltip");
    const tooltip = wrapper.get(".region-tooltip");
    expect(tooltip.html()).toContain("Peak usage: 40.0%");
    expect(tooltip.attributes("style")).toContain("left: 42px");
    expect(tooltip.attributes("style")).toContain("top: 24px");
  });

  it("clears the region tooltip and the hiding class on mouseout", async () => {
    const wrapper = await mountChart();
    handlers["mouseover:markArea"]!({
      seriesName: "Five hours · app-server · account",
      data: { windowIndex: 0 },
      event: { offsetX: 0, offsetY: 0 },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".region-tooltip").exists()).toBe(true);

    handlers["mouseout:markArea"]!({});
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".region-tooltip").exists()).toBe(false);
    expect(wrapper.get(".usage-chart-wrap").classes()).not.toContain("hiding-native-tooltip");
  });

  it("tracks the cursor position via the zrender-level mousemove listener while the region tooltip is active", async () => {
    const wrapper = await mountChart();
    handlers["mouseover:markArea"]!({
      seriesName: "Five hours · app-server · account",
      data: { windowIndex: 0 },
      event: { offsetX: 10, offsetY: 10 },
    });
    await wrapper.vm.$nextTick();

    zrHandlers.mousemove!({ offsetX: 99, offsetY: 88 });
    await wrapper.vm.$nextTick();

    const tooltip = wrapper.get(".region-tooltip");
    expect(tooltip.attributes("style")).toContain("left: 99px");
    expect(tooltip.attributes("style")).toContain("top: 88px");
  });

  it("does nothing when the markArea event carries no matching window/note (no crash, no tooltip)", async () => {
    const wrapper = await mountChart();
    handlers["mouseover:markArea"]!({
      seriesName: "unknown series",
      data: { windowIndex: 0 },
      event: { offsetX: 0, offsetY: 0 },
    });
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".region-tooltip").exists()).toBe(false);
    expect(wrapper.get(".usage-chart-wrap").classes()).not.toContain("hiding-native-tooltip");
  });
});
