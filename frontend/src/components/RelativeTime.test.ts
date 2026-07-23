import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RelativeTime from "./RelativeTime.vue";

describe("RelativeTime", () => {
  it("shows the relative time as text and the absolute time as a native title tooltip", () => {
    const at = new Date("2026-07-17T14:30:00Z");
    const now = new Date("2026-07-17T12:00:00Z");
    const wrapper = mount(RelativeTime, { props: { at, now } });

    expect(wrapper.text()).toBe("in 2h 30m");
    expect(wrapper.attributes("title")).toBe(at.toLocaleString());
  });

  it("defaults `now` to the current time when not provided", () => {
    const at = new Date();
    const wrapper = mount(RelativeTime, { props: { at } });

    expect(wrapper.text()).toBe("just now");
  });
});
