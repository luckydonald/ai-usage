<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";

import { fetchCatalog, fetchSeries } from "./api";
import ServicePanels from "./components/ServicePanels.vue";
import UsageChart from "./components/UsageChart.vue";
import { customRange, paddedChartEnd, presetLabels, rangeForPreset, toDateInputValue, wideningOrder, type TimePreset } from "./time";
import type { Catalog, Filters, GraphSeries } from "./types";

const catalog = ref<Catalog>({ accounts: [], metrics: [], exhausted_color: "#6b7280" });
const series = ref<GraphSeries[]>([]);
const preset = ref<TimePreset>("auto");
const customStartText = ref(toDateInputValue(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)));
const customEndText = ref(toDateInputValue(new Date()));
const loading = ref(true);
const error = ref("");
const connected = ref(false);
const filters = reactive<Filters>({ services: [], providers: [], accounts: [], metrics: [] });
const hiddenSeriesKeys = ref<string[]>([]);
const rangeStart = ref<Date>(new Date());
const rangeEnd = ref<Date>(new Date());
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
const dark = ref(localStorage.getItem("ai-usage-theme") === "dark" || (!localStorage.getItem("ai-usage-theme") && systemDark.matches));
const includeWindowEnds = ref(localStorage.getItem("ai-usage-pad-window-ends") === "true");
const exposed = !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
let events: EventSource | undefined;

const services = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.service))]);
const providers = computed(() => [...new Set(catalog.value.metrics.filter((metric) => !filters.services.length || filters.services.includes(metric.service)).map((metric) => metric.provider))]);
const accounts = computed(() => catalog.value.accounts.filter((account) => (!filters.services.length || filters.services.includes(account.service)) && (!filters.providers.length || filters.providers.includes(account.provider))));
const metricOptions = computed(() => {
  const matching = catalog.value.metrics.filter(
    (metric) =>
      (!filters.services.length || filters.services.includes(metric.service)) &&
      (!filters.providers.length || filters.providers.includes(metric.provider)) &&
      (!filters.accounts.length || filters.accounts.includes(metric.account_id)),
  );
  const seen = new Set<string>();
  const options: { key: string; name: string }[] = [];
  for (const metric of matching) {
    if (seen.has(metric.metric_key)) continue;
    seen.add(metric.metric_key);
    options.push({ key: metric.metric_key, name: metric.metric_name });
  }
  return options;
});

function toggleFilter(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function accountLabel(account: Catalog["accounts"][number]): string {
  const identityLabel = account.identity?.name ?? account.identity?.email;
  return identityLabel ? `${account.name} (${identityLabel})` : account.name;
}

const accountLabels = computed<Record<string, string>>(() =>
  Object.fromEntries(catalog.value.accounts.map((account) => [account.id, accountLabel(account)])),
);

async function load(autoWiden = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [start, end] =
      preset.value === "custom"
        ? customRange(customStartText.value, customEndText.value)
        : rangeForPreset(preset.value);
    rangeStart.value = start;
    series.value = await fetchSeries(start, end, filters);
    rangeEnd.value = paddedChartEnd(preset.value, start, end, series.value, includeWindowEnds.value);
    pruneHiddenSeriesKeys();
    if (autoWiden && preset.value !== "custom" && series.value.every((item) => item.points.length === 0)) {
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

function pruneHiddenSeriesKeys(): void {
  const validKeys = new Set(series.value.map((item) => `${item.account_id}::${item.metric_key}`));
  hiddenSeriesKeys.value = hiddenSeriesKeys.value.filter((key) => validKeys.has(key));
}

function toggleSeries(key: string, visible: boolean): void {
  hiddenSeriesKeys.value = visible
    ? hiddenSeriesKeys.value.filter((existing) => existing !== key)
    : [...new Set([...hiddenSeriesKeys.value, key])];
}

function toggleTheme(): void {
  dark.value = !dark.value;
  localStorage.setItem("ai-usage-theme", dark.value ? "dark" : "light");
}

function toggleIncludeWindowEnds(): void {
  includeWindowEnds.value = !includeWindowEnds.value;
  localStorage.setItem("ai-usage-pad-window-ends", includeWindowEnds.value ? "true" : "false");
  void load();
}

onMounted(async () => {
  try {
    catalog.value = await fetchCatalog();
    await load(true);
    events = new EventSource("/api/v1/events");
    events.addEventListener("open", () => (connected.value = true));
    events.addEventListener("error", () => (connected.value = false));
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
      <h1>AI Usage</h1>
      <div class="header-actions">
        <span class="live" :class="{ connected }"><i /> {{ connected ? "Live" : "Reconnecting…" }}</span>
        <button type="button" class="theme-toggle" @click="toggleTheme">{{ dark ? "Light" : "Dark" }} mode</button>
      </div>
    </header>
    <p v-if="exposed" class="banner banner-error">This dashboard is exposed without authentication.</p>

    <section class="toolbar" aria-label="Graph filters">
      <div class="field">
        <label for="range">Range</label>
        <select id="range" v-model="preset" @change="load()">
          <option v-for="(label, key) in presetLabels" :key="key" :value="key">{{ label }}</option>
        </select>
      </div>
      <div class="field field-checkbox" v-if="preset !== 'custom' && preset !== 'all'">
        <label for="pad-window-ends">
          <input
            id="pad-window-ends"
            type="checkbox"
            :checked="includeWindowEnds"
            @change="toggleIncludeWindowEnds"
          />
          Show every window's end
        </label>
      </div>
      <template v-if="preset === 'custom'">
        <div class="field">
          <label for="range-from">From</label>
          <input id="range-from" type="date" v-model="customStartText" :max="customEndText" @change="load()" />
        </div>
        <div class="field">
          <label for="range-to">To</label>
          <input id="range-to" type="date" v-model="customEndText" :min="customStartText" @change="load()" />
        </div>
      </template>

      <div class="chip-group" v-if="services.length > 1" aria-label="Services">
        <button
          v-for="item in services"
          :key="item"
          type="button"
          class="chip"
          :class="{ active: filters.services.includes(item) }"
          @click="filters.services = toggleFilter(filters.services, item); load()"
        >{{ item }}</button>
      </div>
      <div class="chip-group" v-if="providers.length > 1" aria-label="Providers">
        <button
          v-for="item in providers"
          :key="item"
          type="button"
          class="chip"
          :class="{ active: filters.providers.includes(item) }"
          @click="filters.providers = toggleFilter(filters.providers, item); load()"
        >{{ item }}</button>
      </div>
      <div class="chip-group" v-if="accounts.length > 1" aria-label="Accounts">
        <button
          v-for="item in accounts"
          :key="item.id"
          type="button"
          class="chip"
          :class="{ active: filters.accounts.includes(item.id) }"
          @click="filters.accounts = toggleFilter(filters.accounts, item.id); load()"
        >{{ accountLabel(item) }}</button>
      </div>
      <div class="chip-group" v-if="metricOptions.length > 1" aria-label="Metrics">
        <button
          v-for="item in metricOptions"
          :key="item.key"
          type="button"
          class="chip"
          :class="{ active: filters.metrics.includes(item.key) }"
          @click="filters.metrics = toggleFilter(filters.metrics, item.key); load()"
        >{{ item.name }}</button>
      </div>
    </section>

    <main class="graph-panel">
      <p v-if="loading" class="state">Loading usage history…</p>
      <p v-else-if="error" class="state banner-error">{{ error }}</p>
      <p v-else-if="!series.length" class="state">No usage samples in this range.</p>
      <UsageChart
        v-else
        :series="series"
        :dark="dark"
        :exhausted-color="catalog.exhausted_color"
        :hidden-series-keys="hiddenSeriesKeys"
        :range-start="rangeStart"
        :range-end="rangeEnd"
        :account-labels="accountLabels"
        @toggle-series="toggleSeries"
      />
      <ServicePanels v-if="series.length" :series="series" :account-labels="accountLabels" />
    </main>
  </div>
</template>

<style lang="scss">
@use "./styles/main";
</style>
