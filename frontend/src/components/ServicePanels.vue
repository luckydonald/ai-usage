<script setup lang="ts">
import { computed } from "vue";

import { computeWindowStats, type WindowStats } from "../chart";
import { formatDuration } from "../time";
import type { GraphSeries, GraphWindow } from "../types";
import RelativeTime from "./RelativeTime.vue";

const props = defineProps<{
  series: GraphSeries[];
  accountLabels: Record<string, string>;
  parserLabels: Record<string, string>;
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
  accountId: string;
  accountLabel: string;
  parserLabel: string;
  entries: PanelEntry[];
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
    return {
      service: first!.service,
      accountId: first!.account_id,
      accountLabel: props.accountLabels[first!.account_id] ?? first!.account_id.slice(0, 8),
      parserLabel: props.parserLabels[first!.account_id] ?? first!.provider,
      entries: items.map((item) => {
        const window = item.windows.find((entry) => entry.current) ?? item.windows.at(-1);
        const details = window ? { window, stats: computeWindowStats(item.points, window, now) } : undefined;
        return { item, details };
      }),
    };
  });
});

function entryKey(entry: PanelEntry): string {
  return `${entry.item.account_id}::${entry.item.metric_key}`;
}
</script>

<template>
  <section v-if="panels.length" class="info-panels" aria-label="Service info panels">
    <div v-for="panel in panels" :key="`${panel.service}::${panel.accountId}::${panel.parserLabel}`" class="info-panel">
      <h2>{{ panel.service }} <span class="account-chip">{{ panel.accountLabel }}</span></h2>
      <p class="parser-label" :title="`Configuration ${panel.accountId}`">{{ panel.parserLabel }}</p>
      <div v-for="entry in panel.entries" :key="entryKey(entry)" class="info-panel-metric">
        <h3>{{ entry.item.metric_name }}</h3>
        <template v-if="entry.details">
          <p><RelativeTime :at="new Date(entry.details.window.start)" /> → <RelativeTime :at="new Date(entry.details.window.end)" /></p>
          <p>Peak usage: {{ entry.details.stats.maximumPercentage.toFixed(1) }}%</p>
          <p v-if="entry.details.stats.burnRatePerHour !== null">Burn rate: {{ entry.details.stats.burnRatePerHour.toFixed(1) }}%/h</p>
          <p v-if="entry.details.stats.perfectLanding">Right on spot!</p>
          <template v-else-if="entry.details.window.exhausted_from && entry.details.stats.exhaustedAfterMs !== null && entry.details.stats.blockedForMs !== null">
            <p>Hit 100% after {{ formatDuration(entry.details.stats.exhaustedAfterMs) }}</p>
            <p>Blocked for {{ formatDuration(entry.details.stats.blockedForMs) }}</p>
          </template>
          <p v-else-if="entry.details.stats.remainingPercentageAtEnd !== null">{{ entry.details.stats.remainingPercentageAtEnd.toFixed(1) }}% remaining at window end</p>
          <template v-else-if="entry.details.stats.projectedRemainingPercentageAtEnd !== null">
            <p>Projected to land at {{ (100 - entry.details.stats.projectedRemainingPercentageAtEnd).toFixed(1) }}%</p>
            <p>{{ entry.details.stats.projectedRemainingPercentageAtEnd.toFixed(1) }}% of your limit would be left to use</p>
          </template>
          <p v-else-if="entry.details.stats.projectedExhaustedAt !== null">At this rate, you'll hit 100% around <RelativeTime :at="new Date(entry.details.stats.projectedExhaustedAt)" /></p>
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
    margin: 0 0 .75rem;
    font-size: .95rem;
    font-weight: 700;
    color: var(--text-muted);
  }
}

.account-chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: .15rem .65rem;
  background: var(--surface-muted);
  color: var(--text);
  font-size: .78rem;
  font-weight: 600;
}

.parser-label {
  margin: -.35rem 0 .75rem;
  color: var(--text-muted);
  font-size: .82rem;
  font-weight: 700;
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
    margin: 0 0 .25rem;
    font-size: .85rem;
    font-weight: 700;
    color: var(--text);
  }

  p {
    margin: 0;
  }
}
</style>
