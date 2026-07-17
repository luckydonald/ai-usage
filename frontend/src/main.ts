import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

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
const app = createApp({ template: "<router-view />" });
app.use(router);
initSentry(app, router);
app.mount("#app");

