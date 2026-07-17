import { createApp, h } from "vue";
import { createRouter, createWebHistory, RouterView } from "vue-router";

import App from "./App.vue";
import { initSentry } from "./sentry";
import SentryTestView from "./views/SentryTestView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: App },
    { path: "/__sentry-test", component: SentryTestView },
  ],
});
const app = createApp({ render: () => h(RouterView) });
app.use(router);
initSentry(app, router);
app.mount("#app");
