import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import FilterFunnel from "./FilterFunnel.vue";
import type { FunnelBranch } from "../types";

const tree: FunnelBranch[] = [
  { service: "claude", providers: ["web", "statusline", "usage-cli"] },
  { service: "codex", providers: ["app-server"] },
];

describe("FilterFunnel", () => {
  it("renders one branch per service with its providers nested underneath", () => {
    const wrapper = mount(FilterFunnel, {
      props: { tree, activeServices: [], activeProviders: [] },
    });
    const branches = wrapper.findAll(".funnel-branch");
    expect(branches).toHaveLength(2);
    const claudeBranch = branches[0]!;
    expect(claudeBranch.text()).toContain("claude");
    expect(claudeBranch.text()).toContain("web");
    expect(claudeBranch.text()).toContain("statusline");
    expect(claudeBranch.text()).toContain("usage-cli");
  });

  it("marks the selected service and provider chips as active", () => {
    const wrapper = mount(FilterFunnel, {
      props: { tree, activeServices: ["codex"], activeProviders: ["web"] },
    });
    const codexChip = wrapper.findAll(".chip").find((chip) => chip.text() === "codex");
    const webChip = wrapper.findAll(".chip").find((chip) => chip.text() === "web");
    const statuslineChip = wrapper.findAll(".chip").find((chip) => chip.text() === "statusline");
    expect(codexChip?.classes()).toContain("active");
    expect(webChip?.classes()).toContain("active");
    expect(statuslineChip?.classes()).not.toContain("active");
  });

  it("emits toggle-service and toggle-provider when their chips are clicked", async () => {
    const wrapper = mount(FilterFunnel, {
      props: { tree, activeServices: [], activeProviders: [] },
    });
    await wrapper.findAll(".chip").find((chip) => chip.text() === "codex")!.trigger("click");
    await wrapper.findAll(".chip").find((chip) => chip.text() === "app-server")!.trigger("click");
    expect(wrapper.emitted("toggle-service")).toEqual([["codex"]]);
    expect(wrapper.emitted("toggle-provider")).toEqual([["app-server"]]);
  });
});
