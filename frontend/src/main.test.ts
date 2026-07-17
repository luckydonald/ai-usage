import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

test("mounts the dashboard with the runtime-only Vue build", async () => {
  document.body.innerHTML = '<div id="app"></div>';
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/catalog")) {
        return new Response(JSON.stringify({ accounts: [], metrics: [], exhausted_color: "#6b7280" }));
      }
      return new Response(JSON.stringify([]));
    }),
  );

  await import("./main");

  await vi.waitFor(() => {
    expect(document.querySelector("h1")?.textContent).toBe("AI Usage");
  });
});
