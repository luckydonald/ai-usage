<script setup lang="ts">
import { computed } from "vue";

import { windowTooltipHtml } from "../chart";
import type { GraphSeries, GraphWindow } from "../types";

const props = defineProps<{
  series: GraphSeries[];
  accountLabels: Record<string, string>;
}>();

interface PanelEntry {
  item: GraphSeries;
  window: GraphWindow | undefined;
}

interface ServicePanel {
  service: string;
  accountId: string;
  accountLabel: string;
  entries: PanelEntry[];
}

const panels = computed<ServicePanel[]>(() => {
  const byAccount = new Map<string, GraphSeries[]>();
  for (const item of props.series) {
    const key = `${item.service}::${item.account_id}`;
    const items = byAccount.get(key) ?? [];
    items.push(item);
    byAccount.set(key, items);
  }
  return [...byAccount.values()].map((items) => {
    const [first] = items;
    return {
      service: first!.service,
      accountId: first!.account_id,
      accountLabel: props.accountLabels[first!.account_id] ?? first!.account_id.slice(0, 8),
      entries: items.map((item) => ({
        item,
        window: item.windows.find((window) => window.current) ?? item.windows.at(-1),
      })),
    };
  });
});

function entryKey(entry: PanelEntry): string {
  return `${entry.item.account_id}::${entry.item.metric_key}`;
}

function statsHtml(entry: PanelEntry): string {
  if (!entry.window) return "No window data yet.";
  return windowTooltipHtml(entry.item, entry.window, new Date(), props.accountLabels);
}
</script>

<template>
  <section v-if="panels.length" class="info-panels" aria-label="Service info panels">
    <div v-for="panel in panels" :key="`${panel.service}::${panel.accountId}`" class="info-panel">
      <h2>{{ panel.service }} · {{ panel.accountLabel }}</h2>
      <div v-for="entry in panel.entries" :key="entryKey(entry)" class="info-panel-metric" v-html="statsHtml(entry)" />
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
    margin: 0 0 .75rem;
    font-size: .9rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--text-muted);
  }
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

  :deep(strong) {
    color: var(--text);
  }
}
</style>
