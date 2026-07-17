<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";

import { fetchCatalog, fetchLatest, fetchSeries } from "./api";
import UsageChart from "./components/UsageChart.vue";
import { presetLabels, rangeForPreset, wideningOrder, type TimePreset } from "./time";
import type { Catalog, Filters, GraphSeries, LatestMetric } from "./types";

const catalog = ref<Catalog>({ accounts: [], metrics: [], exhausted_color: "#6b7280" });
const latest = ref<LatestMetric[]>([]);
const series = ref<GraphSeries[]>([]);
const preset = ref<TimePreset>("day");
const loading = ref(true);
const error = ref("");
const filters = reactive<Filters>({ services: [], providers: [], accounts: [], metrics: [] });
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
const dark = ref(localStorage.getItem("ai-usage-theme") === "dark" || (!localStorage.getItem("ai-usage-theme") && systemDark.matches));
const exposed = !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
let events: EventSource | undefined;

const services = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.service))]);
const providers = computed(() => [...new Set(catalog.value.metrics.filter((metric) => !filters.services.length || filters.services.includes(metric.service)).map((metric) => metric.provider))]);
const accounts = computed(() => catalog.value.accounts.filter((account) => (!filters.services.length || filters.services.includes(account.service)) && (!filters.providers.length || filters.providers.includes(account.provider))));
const metrics = computed(() => catalog.value.metrics.filter((metric) => (!filters.services.length || filters.services.includes(metric.service)) && (!filters.providers.length || filters.providers.includes(metric.provider)) && (!filters.accounts.length || filters.accounts.includes(metric.account_id))));

function selectedValues(event: Event): string[] {
  return [...(event.target as HTMLSelectElement).selectedOptions].map((option) => option.value);
}

async function load(autoWiden = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [start, end] = rangeForPreset(preset.value);
    series.value = await fetchSeries(start, end, filters);
    latest.value = await fetchLatest();
    if (autoWiden && series.value.every((item) => item.points.length === 0)) {
      const next = wideningOrder[wideningOrder.indexOf(preset.value) + 1];
      if (next) {
        preset.value = next;
        await load(true);
        return;
      }
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    loading.value = false;
  }
}

function toggleTheme(): void {
  dark.value = !dark.value;
  localStorage.setItem("ai-usage-theme", dark.value ? "dark" : "light");
}

onMounted(async () => {
  try {
    catalog.value = await fetchCatalog();
    await load(true);
    events = new EventSource("/api/v1/events");
    events.addEventListener("sample", () => void load());
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
    loading.value = false;
  }
});
onBeforeUnmount(() => events?.close());
</script>

<template>
  <div class="app" :class="{ dark }">
    <header>
      <div><p class="eyebrow">Local usage telemetry</p><h1>AI Usage</h1></div>
      <button type="button" class="theme" @click="toggleTheme">{{ dark ? "Light" : "Dark" }} mode</button>
    </header>
    <p v-if="exposed" class="warning">This dashboard is exposed without authentication.</p>
    <main>
      <section class="cards" aria-label="Latest usage">
        <article v-for="item in latest" :key="item.event_id">
          <span>{{ item.service }} · {{ item.metric_name }}</span>
          <strong>{{ item.percentage.toFixed(1) }}%</strong>
          <small v-if="item.reset_at">Resets {{ new Date(item.reset_at).toLocaleString() }}</small>
        </article>
      </section>

      <section class="workspace">
        <aside aria-label="Graph filters">
          <label>Range<select v-model="preset" @change="load()"><option v-for="(label, key) in presetLabels" :key="key" :value="key">{{ label }}</option></select></label>
          <label>Services<select multiple @change="filters.services = selectedValues($event); load()"><option v-for="item in services" :key="item">{{ item }}</option></select></label>
          <label>Providers<select multiple @change="filters.providers = selectedValues($event); load()"><option v-for="item in providers" :key="item">{{ item }}</option></select></label>
          <label>Accounts<select multiple @change="filters.accounts = selectedValues($event); load()"><option v-for="item in accounts" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label>Metrics<select multiple @change="filters.metrics = selectedValues($event); load()"><option v-for="item in metrics" :key="`${item.account_id}/${item.metric_key}`" :value="item.metric_key">{{ item.metric_name }}</option></select></label>
        </aside>
        <section class="graph-panel">
          <p v-if="loading" class="state">Loading usage history…</p>
          <p v-else-if="error" class="state error">{{ error }}</p>
          <p v-else-if="!series.length" class="state">No usage samples in this range.</p>
          <UsageChart v-else :series="series" :dark="dark" :exhausted-color="catalog.exhausted_color" />
        </section>
      </section>
    </main>
  </div>
</template>

<style lang="scss">
@use "./styles/main";
</style>

