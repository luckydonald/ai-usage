<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import { fetchCatalog, fetchNotes, fetchSeries } from "./api";
import { activeNotesAt } from "./chart";
import FilterSankey from "./components/FilterSankey.vue";
import ServicePanels from "./components/ServicePanels.vue";
import UsageChart from "./components/UsageChart.vue";
import { defaultFilters, toggleAccount, toggleMetric, toggleProvider, toggleService } from "./filterCascade";
import { renderNoteMarkdown } from "./markdown";
import { customRange, paddedChartEnd, presetLabels, rangeForPreset, toDateInputValue, wideningOrder, type TimePreset } from "./time";
import type { Catalog, Filters, FunnelAccount, FunnelBranch, FunnelProvider, GraphSeries, NoteRange } from "./types";

const catalog = ref<Catalog>({ accounts: [], metrics: [], exhausted_color: "#6b7280", service_icons: {}, provider_icons: {} });
const series = ref<GraphSeries[]>([]);
const notes = ref<NoteRange[]>([]);
const preset = ref<TimePreset>("auto");
const customStartText = ref(toDateInputValue(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)));
const customEndText = ref(toDateInputValue(new Date()));
const loading = ref(true);
const error = ref("");
const connected = ref(false);
// `null` means "no stored value at all" (never customized) — distinct from an explicit empty
// list, which now means "nothing selected in this dimension" (see the `hasEmptyFilterDimension`
// warning below), not "unrestricted" like it used to.
function loadStoredFilters(): Filters | null {
  try {
    const raw = localStorage.getItem("ai-usage-filters");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Filters>;
    return {
      services: Array.isArray(parsed.services) ? parsed.services : [],
      providers: Array.isArray(parsed.providers) ? parsed.providers : [],
      accounts: Array.isArray(parsed.accounts) ? parsed.accounts : [],
      metrics: Array.isArray(parsed.metrics) ? parsed.metrics : [],
    };
  } catch {
    return null;
  }
}

const storedFilters = loadStoredFilters();
const filters = reactive<Filters>(storedFilters ?? { services: [], providers: [], accounts: [], metrics: [] });
// Persisted as one blob (not per-toggle-site setItem calls like the other prefs below) since
// `filters` is a single reactive object toggled from four separate template call sites.
watch(filters, () => localStorage.setItem("ai-usage-filters", JSON.stringify(filters)), { deep: true });
const hiddenSeriesKeys = ref<string[]>([]);
const rangeStart = ref<Date>(new Date());
const rangeEnd = ref<Date>(new Date());
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
const dark = ref(localStorage.getItem("ai-usage-theme") === "dark" || (!localStorage.getItem("ai-usage-theme") && systemDark.matches));
const includeWindowEnds = ref(localStorage.getItem("ai-usage-pad-window-ends") === "true");
const showDataPoints = ref(localStorage.getItem("ai-usage-show-data-points") === "true");
const exposed = !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
let events: EventSource | undefined;

const activeNotes = computed(() => activeNotesAt(notes.value, Date.now()));

// These four are only used to decide whether there's more than one of something worth showing a
// filter diagram for at all (`FilterSankey`'s `v-if` below) — the diagram itself always shows the
// full unfiltered catalog (`serviceProviderTree`), so these don't need to shrink to the current
// selection like they used to for the old flat-chip-list UI.
const services = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.service))]);
const providers = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.provider))]);
// Unfiltered service -> provider -> account -> metric tree (unlike `providers`/`accounts`/
// `metricOptions` above, which shrink to the current selection) so the funnel diagram always
// shows the full structure, with the active selection just highlighted rather than the rest of
// the tree disappearing.
const serviceProviderTree = computed<FunnelBranch[]>(() => {
  const byService = new Map<string, Map<string, Map<string, FunnelAccount["metrics"]>>>();
  for (const metric of catalog.value.metrics) {
    const byProvider = byService.get(metric.service) ?? new Map();
    byService.set(metric.service, byProvider);
    const byAccount = byProvider.get(metric.provider) ?? new Map();
    byProvider.set(metric.provider, byAccount);
    const metrics: FunnelAccount["metrics"] = byAccount.get(metric.account_id) ?? [];
    if (!metrics.some((entry) => entry.key === metric.metric_key)) {
      metrics.push({ key: metric.metric_key, name: metric.metric_name });
    }
    byAccount.set(metric.account_id, metrics);
  }
  return [...byService.entries()].map(([service, byProvider]) => ({
    service,
    providers: [...byProvider.entries()].map(
      ([provider, byAccount]): FunnelProvider => ({
        provider,
        accounts: [...byAccount.entries()].map(([accountId, metrics]) => ({
          id: accountId,
          label: accountLabels.value[accountId] ?? accountId.slice(0, 8),
          metrics,
        })),
      }),
    ),
  }));
});
const accounts = computed(() => catalog.value.accounts);
const metricOptions = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.metric_key))]);

// Empty now means "nothing selected in this dimension" (not "unrestricted" like it used to) —
// with everything on by default (see `defaultFilters` below), the only way to get here is
// deliberately deselecting every chip in a column, so it's worth a distinct explanation rather
// than just silently showing no data.
const hasEmptyFilterDimension = computed(() => !filters.services.length || !filters.providers.length || !filters.accounts.length || !filters.metrics.length);

function accountLabel(account: Catalog["accounts"][number]): string {
  const identityLabel = account.identity?.name ?? account.identity?.email;
  return identityLabel ? `${account.name} (${identityLabel})` : account.name;
}

const accountLabels = computed<Record<string, string>>(() => {
  const labels: Record<string, string> = {};
  const groupLabelSource = new Map<string, Catalog["accounts"][number]>();
  for (const account of catalog.value.accounts) {
    labels[account.id] = accountLabel(account);
    if (account.group_id && !groupLabelSource.has(account.group_id)) {
      groupLabelSource.set(account.group_id, account);
    }
  }
  for (const [groupId, account] of groupLabelSource) {
    labels[groupId] = accountLabel(account);
  }
  return labels;
});

interface LoadOptions {
  autoWiden?: boolean;
  silent?: boolean;
}

async function performLoad({ autoWiden = false, silent = false }: LoadOptions): Promise<void> {
  if (!silent) {
    loading.value = true;
    error.value = "";
  }
  // An empty dimension now means "nothing selected" (not "unrestricted") — sending the request
  // anyway would omit that filter's query param entirely, which the backend reads as
  // unrestricted, showing everything instead of the intended nothing.
  if (hasEmptyFilterDimension.value) {
    series.value = [];
    if (!silent) loading.value = false;
    return;
  }
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
        await performLoad({ autoWiden: true, silent });
        return;
      }
    }
  } catch (reason) {
    if (silent) {
      console.error("background refresh failed, keeping last chart", reason);
    } else {
      error.value = reason instanceof Error ? reason.message : String(reason);
    }
  } finally {
    if (!silent) loading.value = false;
  }
}

async function load(autoWiden = false): Promise<void> {
  await performLoad({ autoWiden });
}

async function loadSilently(): Promise<void> {
  await performLoad({ silent: true });
}

async function loadNotes(): Promise<void> {
  notes.value = await fetchNotes();
}

// Drops filter values that no longer exist in the catalog (e.g. a removed account restored
// from an older localStorage snapshot) — otherwise a stale selection would silently filter the
// chart down to nothing with no matching chip left to click to undo it.
function pruneStoredFilters(): void {
  const validServices = new Set(catalog.value.metrics.map((metric) => metric.service));
  const validProviders = new Set(catalog.value.metrics.map((metric) => metric.provider));
  const validAccounts = new Set(catalog.value.accounts.map((account) => account.id));
  const validMetrics = new Set(catalog.value.metrics.map((metric) => metric.metric_key));
  filters.services = filters.services.filter((value) => validServices.has(value));
  filters.providers = filters.providers.filter((value) => validProviders.has(value));
  filters.accounts = filters.accounts.filter((value) => validAccounts.has(value));
  filters.metrics = filters.metrics.filter((value) => validMetrics.has(value));
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

function applyFilters(next: Filters): void {
  filters.services = next.services;
  filters.providers = next.providers;
  filters.accounts = next.accounts;
  filters.metrics = next.metrics;
  void load();
}

function onToggleService(service: string): void {
  applyFilters(toggleService(serviceProviderTree.value, filters, service));
}

function onToggleProvider(provider: string): void {
  applyFilters(toggleProvider(serviceProviderTree.value, filters, provider));
}

function onToggleAccount(accountId: string): void {
  applyFilters(toggleAccount(serviceProviderTree.value, filters, accountId));
}

function onToggleMetric(metricKey: string): void {
  applyFilters(toggleMetric(serviceProviderTree.value, filters, metricKey));
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

function toggleShowDataPoints(): void {
  showDataPoints.value = !showDataPoints.value;
  localStorage.setItem("ai-usage-show-data-points", showDataPoints.value ? "true" : "false");
}

onMounted(async () => {
  try {
    catalog.value = await fetchCatalog();
    if (!storedFilters) {
      const initial = defaultFilters(serviceProviderTree.value);
      filters.services = initial.services;
      filters.providers = initial.providers;
      filters.accounts = initial.accounts;
      filters.metrics = initial.metrics;
    } else {
      pruneStoredFilters();
    }
    await Promise.all([load(true), loadNotes()]);
    events = new EventSource("/api/v1/events");
    events.addEventListener("open", () => (connected.value = true));
    events.addEventListener("error", () => (connected.value = false));
    events.addEventListener("sample", () => {
      void loadSilently();
      void loadNotes();
    });
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
    <p v-for="note in activeNotes" :key="`${note.service}-${note.account_id}-${note.start}`" class="banner banner-info" v-html="renderNoteMarkdown(note.text)" />

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
      <div class="field field-checkbox">
        <label for="show-data-points">
          <input
            id="show-data-points"
            type="checkbox"
            :checked="showDataPoints"
            @change="toggleShowDataPoints"
          />
          Show data points
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

      <FilterSankey
        v-if="services.length > 1 || providers.length > 1 || accounts.length > 1 || metricOptions.length > 1"
        :tree="serviceProviderTree"
        :active-services="filters.services"
        :active-providers="filters.providers"
        :active-accounts="filters.accounts"
        :active-metrics="filters.metrics"
        :dark="dark"
        :service-icons="catalog.service_icons"
        :provider-icons="catalog.provider_icons"
        @toggle-service="onToggleService"
        @toggle-provider="onToggleProvider"
        @toggle-account="onToggleAccount"
        @toggle-metric="onToggleMetric"
      />
    </section>

    <main class="graph-panel">
      <p v-if="loading" class="state">Loading usage history…</p>
      <p v-else-if="error" class="state banner-error">{{ error }}</p>
      <p v-else-if="hasEmptyFilterDimension" class="state banner-warning">Nothing selected in at least one filter — deselect fewer things to see data.</p>
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
        :notes="notes"
        :show-data-points="showDataPoints"
        @toggle-series="toggleSeries"
      />
      <ServicePanels v-if="series.length" :series="series" :account-labels="accountLabels" />
    </main>
  </div>
</template>

<style lang="scss">
@use "./styles/main";
</style>
