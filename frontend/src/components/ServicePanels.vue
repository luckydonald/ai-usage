<script setup lang="ts">
import { computed, reactive } from "vue";

import { computeWindowStats, type WindowStats } from "../chart";
import { formatDuration } from "../time";
import { stripServicePrefix } from "../sankey";
import type { AccountIdentity, GraphSeries, GraphWindow, IconRef } from "../types";
import Icon from "./Icon.vue";
import RelativeTime from "./RelativeTime.vue";

const props = defineProps<{
  series: GraphSeries[];
  accountLabels: Record<string, string>;
  parserLabels: Record<string, string>;
  accountIdentities: Record<string, AccountIdentity | null>;
  serviceIcons: Record<string, IconRef>;
  providerIcons: Record<string, IconRef>;
  metricIcons: Record<string, IconRef>;
}>();

interface EntryDetails {
  window: GraphWindow;
  stats: WindowStats;
}

interface PanelEntry {
  item: GraphSeries;
  details: EntryDetails | undefined;
}

interface ServicePanel {
  service: string;
  provider: string;
  accountId: string;
  accountLabel: string;
  parserLabel: string;
  favicon: string | undefined;
  entries: PanelEntry[];
}

const EMAIL_PATTERN = /^[^\s@]+@([^\s@]+\.[^\s@]+)$/;

function domainFor(accountId: string, identity: AccountIdentity | null | undefined): string | undefined {
  const email = identity?.email ?? accountId;
  return EMAIL_PATTERN.exec(email)?.[1];
}

const panels = computed<ServicePanel[]>(() => {
  const byAccount = new Map<string, GraphSeries[]>();
  for (const item of props.series) {
    const key = `${item.service}::${item.account_id}::${item.provider}`;
    const items = byAccount.get(key) ?? [];
    items.push(item);
    byAccount.set(key, items);
  }
  const now = new Date();
  return [...byAccount.values()].map((items) => {
    const [first] = items;
    const accountId = first!.account_id;
    const domain = domainFor(accountId, props.accountIdentities[accountId]);
    return {
      service: first!.service,
      provider: first!.provider,
      accountId,
      accountLabel: props.accountLabels[accountId] ?? accountId.slice(0, 8),
      parserLabel: stripServicePrefix(first!.service, props.parserLabels[accountId] ?? first!.provider),
      favicon: domain ? `/img/favicon/${domain}` : undefined,
      entries: items.map((item) => {
        const window = item.windows.find((entry) => entry.current) ?? item.windows.at(-1);
        const details = window ? { window, stats: computeWindowStats(item.points, window, now) } : undefined;
        return { item, details };
      }),
    };
  });
});

// Tracks accounts whose favicon 404'd/errored, so the template swaps to the generic user icon
// instead of leaving a broken <img>.
const brokenFavicons = reactive(new Set<string>());
function faviconFailed(accountId: string): void {
  brokenFavicons.add(accountId);
}

function entryKey(entry: PanelEntry): string {
  return `${entry.item.account_id}::${entry.item.metric_key}`;
}

const USER_ICON: IconRef = { set: "solid", name: "user", pack: "fontawesome-free-pack", version: "latest" };
const PEAK_ICON: IconRef = { set: "solid", name: "gauge-high", pack: "fontawesome-free-pack", version: "latest" };
const BURN_ICON: IconRef = { set: "solid", name: "fire", pack: "fontawesome-free-pack", version: "latest" };
const PERFECT_ICON: IconRef = { set: "solid", name: "bullseye", pack: "fontawesome-free-pack", version: "latest" };
const EXHAUSTED_ICON: IconRef = { set: "solid", name: "triangle-exclamation", pack: "fontawesome-free-pack", version: "latest" };
const BLOCKED_ICON: IconRef = { set: "solid", name: "ban", pack: "fontawesome-free-pack", version: "latest" };
const REMAINING_ICON: IconRef = { set: "solid", name: "battery-half", pack: "fontawesome-free-pack", version: "latest" };
const PROJECTED_ICON: IconRef = { set: "solid", name: "chart-line", pack: "fontawesome-free-pack", version: "latest" };
</script>

<template>
  <section v-if="panels.length" class="info-panels" aria-label="Service info panels">
    <div v-for="panel in panels" :key="`${panel.service}::${panel.accountId}::${panel.parserLabel}`" class="info-panel">
      <h2>
        {{ panel.service }}
        <Icon v-if="serviceIcons[panel.service]" v-bind="serviceIcons[panel.service]!" :title="panel.service" class="service-mark" />
      </h2>
      <div class="badge-row">
        <span class="chip-badge" :title="`Configuration ${panel.accountId}`">
          <Icon v-if="providerIcons[panel.provider]" v-bind="providerIcons[panel.provider]!" />
          {{ panel.parserLabel }}
        </span>
        <span class="chip-badge" :title="panel.accountId">
          <img
            v-if="panel.favicon && !brokenFavicons.has(panel.accountId)"
            :src="panel.favicon"
            alt=""
            class="account-favicon"
            @error="faviconFailed(panel.accountId)"
          />
          <Icon v-else v-bind="USER_ICON" color="var(--color-primary)" />
          {{ panel.accountLabel }}
        </span>
      </div>
      <div v-for="entry in panel.entries" :key="entryKey(entry)" class="info-panel-metric">
        <h3>
          {{ entry.item.metric_name }}
          <Icon v-if="metricIcons[entry.item.metric_key]" v-bind="metricIcons[entry.item.metric_key]!" />
        </h3>
        <template v-if="entry.details">
          <p><RelativeTime :at="new Date(entry.details.window.start)" /> → <RelativeTime :at="new Date(entry.details.window.end)" /></p>
          <p><Icon v-bind="PEAK_ICON" /> Peak usage: {{ entry.details.stats.maximumPercentage.toFixed(1) }}%</p>
          <p v-if="entry.details.stats.burnRatePerHour !== null"><Icon v-bind="BURN_ICON" /> Burn rate: {{ entry.details.stats.burnRatePerHour.toFixed(1) }}%/h</p>
          <p v-if="entry.details.stats.perfectLanding"><Icon v-bind="PERFECT_ICON" /> Right on spot!</p>
          <template v-else-if="entry.details.window.exhausted_from && entry.details.stats.exhaustedAfterMs !== null && entry.details.stats.blockedForMs !== null">
            <p><Icon v-bind="EXHAUSTED_ICON" /> Hit 100% after {{ formatDuration(entry.details.stats.exhaustedAfterMs) }}</p>
            <p><Icon v-bind="BLOCKED_ICON" /> Blocked for {{ formatDuration(entry.details.stats.blockedForMs) }}</p>
          </template>
          <p v-else-if="entry.details.stats.remainingPercentageAtEnd !== null"><Icon v-bind="REMAINING_ICON" /> {{ entry.details.stats.remainingPercentageAtEnd.toFixed(1) }}% remaining at window end</p>
          <template v-else-if="entry.details.stats.projectedRemainingPercentageAtEnd !== null">
            <p><Icon v-bind="PROJECTED_ICON" /> Projected to land at {{ (100 - entry.details.stats.projectedRemainingPercentageAtEnd).toFixed(1) }}%</p>
            <p>{{ entry.details.stats.projectedRemainingPercentageAtEnd.toFixed(1) }}% of your limit would be left to use</p>
          </template>
          <p v-else-if="entry.details.stats.projectedExhaustedAt !== null"><Icon v-bind="PROJECTED_ICON" /> At this rate, you'll hit 100% around <RelativeTime :at="new Date(entry.details.stats.projectedExhaustedAt)" /></p>
        </template>
        <p v-else>No window data yet.</p>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.info-panels {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 1rem;
}

.info-panel {
  flex: 1 1 16rem;
  min-width: 16rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 1rem;
  padding: 1rem 1.25rem;
  box-shadow: 0 12px 38px rgb(15 10 35 / 6%);

  h2 {
    display: flex;
    align-items: center;
    gap: .5rem;
    margin: 0 0 .5rem;
  }
}

.service-mark {
  width: 1.4rem;
  height: 1.4rem;

  :deep(.icon) {
    width: 1rem;
    height: 1rem;
  }
}

.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
  margin: 0 0 .75rem;
}

.chip-badge {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: .15rem .65rem;
  background: var(--surface-muted);
  color: var(--text);
  font-size: .78rem;
  font-weight: 600;
}

.account-favicon {
  width: .9rem;
  height: .9rem;
  border-radius: 2px;
}

.info-panel-metric {
  font-size: .85rem;
  line-height: 1.5;
  color: var(--text);

  & + .info-panel-metric {
    margin-top: .75rem;
    padding-top: .75rem;
    border-top: 1px solid var(--border);
  }

  h3 {
    display: flex;
    align-items: center;
    gap: .35rem;
    margin: 0 0 .25rem;
    font-size: .85rem;
    font-weight: 700;
    color: var(--text);
  }

  p {
    margin: 0;
    display: flex;
    align-items: center;
    gap: .35rem;
  }
}
</style>
