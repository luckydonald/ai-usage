import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

import { sentryVitePlugin } from "@sentry/vite-plugin";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

function commandValue(...args: string[]): string {
  try {
    return execFileSync(args[0] ?? "", args.slice(1), { encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

function fileValue(name: string): string {
  const path = fileURLToPath(new URL(`../${name}`, import.meta.url));
  return existsSync(path) ? readFileSync(path, "utf8").trim() : "";
}

const commit = process.env.SOURCE_COMMIT || commandValue("git", "rev-parse", "HEAD") || fileValue("git-commit.txt") || "unknown";
const branch = process.env.GIT_BRANCH || commandValue("git", "rev-parse", "--abbrev-ref", "HEAD") || fileValue("git-branch.txt") || "unknown";
const buildTime = process.env.BUILD_TIME || fileValue("build-time.txt") || new Date().toISOString();
const uploadSourcemaps = Boolean(
  process.env.BUILD_BUGSINK_URL &&
    process.env.BUILD_BUGSINK_AUTH_TOKEN &&
    process.env.BUILD_BUGSINK_PROJECT_SLUG,
);

export default defineConfig({
  plugins: [
    vue(),
    uploadSourcemaps
      ? sentryVitePlugin({
          url: process.env.BUILD_BUGSINK_URL,
          authToken: process.env.BUILD_BUGSINK_AUTH_TOKEN,
          org: "none",
          project: process.env.BUILD_BUGSINK_PROJECT_SLUG,
          release: { name: commit, create: false, finalize: false },
          sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] },
        })
      : null,
  ],
  define: {
    __GIT_COMMIT_FULL__: JSON.stringify(commit),
    __GIT_BRANCH__: JSON.stringify(branch),
    __BUILD_TIME__: JSON.stringify(buildTime),
  },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: { sourcemap: true },
  test: {
    environment: "happy-dom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
