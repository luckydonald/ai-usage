import * as Sentry from "@sentry/vue";
import type { App } from "vue";
import type { Router } from "vue-router";

function traceSampleRate(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : 0;
}

export function initSentry(app: App, router: Router): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    app,
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || undefined,
    release: import.meta.env.VITE_SENTRY_RELEASE || __GIT_COMMIT_FULL__,
    dist: __BUILD_TIME__,
    integrations: [Sentry.browserTracingIntegration({ router }), Sentry.vueIntegration({ app })],
    sendDefaultPii: false,
    initialScope: {
      tags: { git_commit: __GIT_COMMIT_FULL__, git_branch: __GIT_BRANCH__, build_time: __BUILD_TIME__ },
    },
    tracesSampleRate: traceSampleRate(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE),
  });
}

