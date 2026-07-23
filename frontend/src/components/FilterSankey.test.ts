import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

const chart = vi.hoisted(() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() }));
vi.mock("echarts/core", () => ({ init: vi.fn(() => chart), use: vi.fn() }));

import FilterSankey from "./FilterSankey.vue";
import Chip from "./Chip.vue";
import type { SankeyService } from "../types";

const tree: SankeyService[] = [{
  service: "claude",
  accounts: [{ id: "user@example.com", label: "user@example.com", organizations: [{ id: "org", name: "Work", parsers: [{ id: "config", provider: "web", label: "Web", metrics: [{ key: "five-hours", name: "Five hours" }] }] }] }],
}];

async function mountSankey() {
  const wrapper = mount(FilterSankey, { props: { tree, activeAccounts: ["config"], activeMetrics: ["five-hours"], dark: false } });
  await flushPromises();
  return wrapper;
}

afterEach(() => vi.clearAllMocks());

describe("FilterSankey", () => {
  it("renders parser labels while retaining config UUID in the title", async () => {
    const wrapper = await mountSankey();
    const parser = wrapper.findAllComponents(Chip).find((chip) => chip.props("label") === "Web");
    expect(parser?.props("title")).toBe("Configuration config");
  });

  it("emits the exact configuration when a parser chip is clicked", async () => {
    const wrapper = await mountSankey();
    await wrapper.findAllComponents(Chip).find((chip) => chip.props("label") === "Web")!.trigger("click");
    expect(wrapper.emitted("toggle-parser")).toEqual([["config"]]);
  });
});
