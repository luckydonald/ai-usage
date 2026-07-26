<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import { fetchCatalog, fetchLegacySeries, fetchNotes, fetchSeries } from "./api";
import { activeNotesAt } from "./chart";
import FilterSankey from "./components/FilterSankey.vue";
import ServicePanels from "./components/ServicePanels.vue";
import UsageChart from "./components/UsageChart.vue";
import { defaultFilters, toggleAccount, toggleMetric, toggleOrganization, toggleParser, toggleService } from "./filterCascade";
import { renderNoteMarkdown } from "./markdown";
import { stripServicePrefix } from "./sankey";
import { customRange, paddedChartEnd, presetLabels, rangeForPreset, toDateInputValue, wideningOrder, type TimePreset } from "./time";
import type { AccountIdentity, Catalog, Filters, GraphSeries, NoteRange, SankeyParser, SankeyService } from "./types";

const catalog = ref<Catalog>({ accounts: [], metrics: [], exhausted_color: "#6b7280", service_icons: {}, provider_icons: {}, metric_icons: {} });
const series = ref<GraphSeries[]>([]);
const detailedSeries = ref<GraphSeries[]>([]);
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
      accounts: Array.isArray(parsed.accounts) ? parsed.accounts : [],
      metrics: Array.isArray(parsed.metrics) ? parsed.metrics : [],
    };
  } catch {
    return null;
  }
}

const storedFilters = loadStoredFilters();
const filters = reactive<Filters>(storedFilters ?? { accounts: [], metrics: [] });
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
const aggregation = ref<"raw" | "legacy">(localStorage.getItem("ai-usage-chart-aggregation") === "legacy" ? "legacy" : "raw");
const exposed = !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
let events: EventSource | undefined;

const activeNotes = computed(() => activeNotesAt(notes.value, Date.now()));

const services = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.service))]);
const sankeyTree = computed<SankeyService[]>(() => {
  const byService = new Map<string, Map<string, Map<string, Map<string, SankeyParser>>>>();
  for (const metric of catalog.value.metrics) {
    const configured = catalog.value.accounts.find((account) => account.id === metric.account_id);
    if (!configured) continue;
    const accountId = configured.account.login ?? `unresolved:${configured.id}`;
    const organizationId = configured.account.organization?.id ?? null;
    const organizationKey = organizationId ?? `unorganized:${configured.id}`;
    const byAccount = byService.get(metric.service) ?? new Map();
    byService.set(metric.service, byAccount);
    const byOrganization = byAccount.get(accountId) ?? new Map();
    byAccount.set(accountId, byOrganization);
    const parsers = byOrganization.get(organizationKey) ?? new Map();
    byOrganization.set(organizationKey, parsers);
    const parser: SankeyParser = parsers.get(configured.id) ?? {
      id: configured.id,
      provider: configured.provider,
      label: configured.parser_label,
      icon: catalog.value.provider_icons[configured.provider],
      metrics: [],
    };
    if (!parser.metrics.some((entry) => entry.key === metric.metric_key)) {
      parser.metrics.push({
        key: metric.metric_key,
        name: metric.metric_name,
        icon: catalog.value.metric_icons[metric.metric_key],
      });
    }
    parsers.set(configured.id, parser);
  }
  return [...byService.entries()].map(([service, byAccount]) => ({
    service,
    accounts: [...byAccount.entries()].map(([accountId, byOrganization]) => ({
      id: accountId,
      label: accountId.startsWith("unresolved:") ? "Unresolved configuration" : accountId,
      organizations: [...byOrganization.entries()].map(([organizationKey, parsers]) => {
        const first = parsers.values().next().value as SankeyParser;
        const configured = catalog.value.accounts.find((account) => account.id === first.id)!;
        return {
          id: configured.account.organization?.id ?? null,
          name: configured.account.organization?.name ?? null,
          parsers: [...parsers.values()],
        };
      }),
    })),
  }));
});
const accounts = computed(() => catalog.value.accounts);
const metricOptions = computed(() => [...new Set(catalog.value.metrics.map((metric) => metric.metric_key))]);

// Empty now means "nothing selected in this dimension" (not "unrestricted" like it used to) —
// with everything on by default (see `defaultFilters` below), the only way to get here is
// deliberately deselecting every chip in a column, so it's worth a distinct explanation rather
// than just silently showing no data.
const hasEmptyFilterDimension = computed(() => !filters.accounts.length || !filters.metrics.length);

function accountLabel(account: Catalog["accounts"][number]): string {
  return account.account.login ?? `Unresolved configuration (${account.id.slice(0, 8)})`;
}

const accountLabels = computed<Record<string, string>>(() => {
  const labels: Record<string, string> = {};
  for (const account of catalog.value.accounts) {
    labels[account.id] = accountLabel(account);
  }
  return labels;
});

const parserLabels = computed<Record<string, string>>(
  () => Object.fromEntries(catalog.value.accounts.map((account) => [account.id, account.parser_label])),
);

const accountIdentities = computed<Record<string, AccountIdentity | null>>(
  () => Object.fromEntries(catalog.value.accounts.map((account) => [account.id, account.identity])),
);

const chartLabels = computed<Record<string, string>>(() =>
  Object.fromEntries(
    catalog.value.accounts.map((account) => {
      const organization = account.account.organization?.name;
      const parserLabel = stripServicePrefix(account.service, account.parser_label);
      return [account.id, [accountLabel(account), organization, parserLabel].filter(Boolean).join(" · ")];
    }),
  ),
);

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
    detailedSeries.value = await fetchSeries(start, end, filters);
    series.value = aggregation.value === "legacy" ? await fetchLegacySeries(start, end, filters) : detailedSeries.value;
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
  const validAccounts = new Set(catalog.value.accounts.map((account) => account.id));
  const validMetrics = new Set(catalog.value.metrics.map((metric) => metric.metric_key));
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
  filters.accounts = next.accounts;
  filters.metrics = next.metrics;
  void load();
}

function onToggleService(serviceId: string): void {
  const service = sankeyTree.value.find((entry) => entry.service === serviceId);
  if (service) applyFilters(toggleService(filters, service));
}

function onToggleAccount(accountId: string): void {
  const account = sankeyTree.value.flatMap((service) => service.accounts).find((entry) => entry.id === accountId);
  if (account) applyFilters(toggleAccount(filters, account));
}

function onToggleOrganization(organizationId: string): void {
  const organization = sankeyTree.value.flatMap((service) => service.accounts).flatMap((account) => account.organizations).find((entry) => entry.id === organizationId);
  if (organization) applyFilters(toggleOrganization(filters, organization));
}

function onToggleParser(configId: string): void {
  const parser = sankeyTree.value.flatMap((service) => service.accounts).flatMap((account) => account.organizations).flatMap((organization) => organization.parsers).find((entry) => entry.id === configId);
  if (parser) applyFilters(toggleParser(filters, parser));
}

function onToggleMetric(metricKey: string): void {
  applyFilters(toggleMetric(filters, metricKey));
}

function setAggregation(): void {
  localStorage.setItem("ai-usage-chart-aggregation", aggregation.value);
  void load();
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
      const initial = defaultFilters(sankeyTree.value);
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
        v-if="services.length > 1 || accounts.length > 1 || metricOptions.length > 1"
        :tree="sankeyTree"
        :active-accounts="filters.accounts"
        :active-metrics="filters.metrics"
        :dark="dark"
        :service-icons="catalog.service_icons"
        :metric-icons="catalog.metric_icons"
        @toggle-service="onToggleService"
        @toggle-account="onToggleAccount"
        @toggle-organization="onToggleOrganization"
        @toggle-parser="onToggleParser"
        @toggle-metric="onToggleMetric"
      />
    </section>

    <main class="graph-panel">
      <div class="chart-mode" role="group" aria-label="Chart aggregation">
        <button type="button" :class="{ active: aggregation === 'raw' }" @click="aggregation = 'raw'; setAggregation()">Detailed</button>
        <button type="button" :class="{ active: aggregation === 'legacy' }" @click="aggregation = 'legacy'; setAggregation()">Combined</button>
      </div>
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
        :account-labels="chartLabels"
        :service-icons="catalog.service_icons"
        :metric-icons="catalog.metric_icons"
        :notes="notes"
        :show-data-points="showDataPoints"
        @toggle-series="toggleSeries"
      />
      <ServicePanels
        v-if="detailedSeries.length"
        :series="detailedSeries"
        :account-labels="accountLabels"
        :parser-labels="parserLabels"
        :account-identities="accountIdentities"
        :service-icons="catalog.service_icons"
        :provider-icons="catalog.provider_icons"
        :metric-icons="catalog.metric_icons"
      />
    </main>
  </div>
</template>

<style lang="scss">
@use "./styles/main";
</style>
