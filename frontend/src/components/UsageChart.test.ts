import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

const chart = vi.hoisted(() => ({
  containPixel: vi.fn(() => true),
  // Mirrors real echarts: a `{ gridIndex }` finder returns a `[x, y]` pair; a lone
  // `{ xAxisIndex }` finder returns a single (unusable-here) NaN, catching a regression
  // to the wrong finder shape that silently broke click-to-pin.
  convertFromPixel: vi.fn((finder: { gridIndex?: number; xAxisIndex?: number }) =>
    "gridIndex" in finder ? [new Date("2026-07-17T10:00:00Z").getTime(), 50] : NaN,
  ),
  dispatchAction: vi.fn(),
  dispose: vi.fn(),
  getZr: vi.fn(() => ({ on: vi.fn() })),
  on: vi.fn(),
  resize: vi.fn(),
  setOption: vi.fn(),
}));

vi.mock("echarts/core", () => ({
  init: vi.fn(() => chart),
  use: vi.fn(),
}));

import UsageChart from "./UsageChart.vue";

const series = [{
  service: "codex",
  provider: "app-server",
  account_id: "account",
  metric_key: "five-hours",
  metric_name: "Five hours",
  color: "#f97316",
  points: [{ at: "2026-07-17T10:00:00Z", percentage: 20, current: null, maximum: null }],
  windows: [],
}];

function mountChart() {
  return mount(UsageChart, {
    attachTo: document.body,
    props: {
      series,
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

afterEach(() => {
  document.body.innerHTML = "";
  document.body.style.overflow = "";
  vi.clearAllMocks();
});

function clickChart(): void {
  const zr = chart.getZr.mock.results[0]?.value;
  const click = zr.on.mock.calls.find(([eventName]: [string]) => eventName === "click")?.[1] as ((event: { offsetX: number; offsetY: number }) => void) | undefined;
  if (!click) throw new Error("chart click handler must be registered");
  click({ offsetX: 100, offsetY: 100 });
}

describe("UsageChart pinned tooltip", () => {
  it("opens a scrollable overlay from a click in the plot and closes it again", async () => {
    const wrapper = mountChart();
    clickChart();
    await flushPromises();

    const overlay = document.querySelector<HTMLElement>(".tooltip-overlay");
    expect(overlay).not.toBeNull();
    expect(overlay?.textContent).toContain("Five hours: 20.0%");
    expect(chart.dispatchAction).toHaveBeenCalledWith({ type: "hideTip" });

    const closeButton = document.querySelector<HTMLButtonElement>(".pinned-tooltip-close");
    if (!closeButton) throw new Error("pinned tooltip close button must be rendered");
    closeButton.click();
    await wrapper.vm.$nextTick();
    expect(document.querySelector(".tooltip-overlay")).toBeNull();
  });

  it("disables body scroll while the overlay is open and restores it on close", async () => {
    const wrapper = mountChart();
    expect(document.body.style.overflow).toBe("");

    clickChart();
    await flushPromises();
    expect(document.body.style.overflow).toBe("hidden");

    document.querySelector<HTMLButtonElement>(".pinned-tooltip-close")!.click();
    await wrapper.vm.$nextTick();
    expect(document.body.style.overflow).toBe("");
  });

  it("restores body scroll if the component unmounts while the overlay is open", async () => {
    const wrapper = mountChart();
    clickChart();
    await flushPromises();
    expect(document.body.style.overflow).toBe("hidden");

    wrapper.unmount();
    expect(document.body.style.overflow).toBe("");
  });
});
