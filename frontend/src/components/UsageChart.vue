<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { chartOption, type MarkAreaHoverEvent, regionTooltipHtml, seriesDisplayName, seriesKey } from "../chart";
import type { GraphSeries, NoteRange } from "../types";

const props = defineProps<{
  series: GraphSeries[];
  dark: boolean;
  exhaustedColor: string;
  hiddenSeriesKeys: string[];
  rangeStart: Date;
  rangeEnd: Date;
  accountLabels: Record<string, string>;
  notes: NoteRange[];
  showDataPoints: boolean;
}>();
const emit = defineEmits<{ (event: "toggle-series", key: string, visible: boolean): void }>();
const container = ref<HTMLDivElement>();
const regionTooltip = ref<{ html: string; x: number; y: number } | null>(null);
let chart: echarts.ECharts | undefined;

function legendSelected(): Record<string, boolean> {
  const selected: Record<string, boolean> = {};
  for (const item of props.series) {
    selected[seriesDisplayName(item, props.accountLabels)] = !props.hiddenSeriesKeys.includes(seriesKey(item));
  }
  return selected;
}

function render(recreate: boolean): void {
  if (!container.value) return;
  if (recreate) {
    chart?.dispose();
    chart = undefined;
  }
  const isNew = !chart;
  chart ??= echarts.init(container.value, props.dark ? "dark" : undefined);
  chart.setOption(
    chartOption(props.series, props.dark, props.exhaustedColor, {
      legendSelected: legendSelected(),
      start: props.rangeStart,
      end: props.rangeEnd,
      animate: recreate || isNew,
      accountLabels: props.accountLabels,
      notes: props.notes,
      showDataPoints: props.showDataPoints,
    }),
    recreate || isNew,
  );
  if (isNew) {
    chart.on("legendselectchanged", (raw: unknown) => {
      const params = raw as { name: string; selected: Record<string, boolean> };
      const item = props.series.find((entry) => seriesDisplayName(entry, props.accountLabels) === params.name);
      const visible = params.selected[params.name] ?? true;
      if (item) emit("toggle-series", seriesKey(item), visible);
    });
    // Under `tooltip.trigger: "axis"`, ECharts' built-in tooltip never fires for markArea
    // hover (window backgrounds, notes bands) anymore — it's always superseded by the
    // axis-trigger slice. Render that content ourselves via a manually-positioned div,
    // and hide the built-in tooltip while doing so to avoid both showing at once.
    chart.on("mouseover", { componentType: "markArea" }, (raw: unknown) => {
      const params = raw as MarkAreaHoverEvent & { event?: { offsetX: number; offsetY: number } };
      const html = regionTooltipHtml(props.series, params, new Date(), props.accountLabels, props.notes);
      if (html && params.event) {
        regionTooltip.value = { html, x: params.event.offsetX, y: params.event.offsetY };
        chart?.dispatchAction({ type: "hideTip" });
      }
    });
    chart.on("mouseout", { componentType: "markArea" }, () => {
      regionTooltip.value = null;
    });
    chart.getZr().on("mousemove", (raw: unknown) => {
      if (!regionTooltip.value) return;
      const event = raw as { offsetX: number; offsetY: number };
      regionTooltip.value = { ...regionTooltip.value, x: event.offsetX, y: event.offsetY };
      chart?.dispatchAction({ type: "hideTip" });
    });
  }
}

function resize(): void {
  chart?.resize();
}

onMounted(() => {
  render(false);
  window.addEventListener("resize", resize);
});
watch(() => props.dark, () => render(true));
watch(
  () => [
    props.series,
    props.exhaustedColor,
    props.hiddenSeriesKeys,
    props.rangeStart,
    props.rangeEnd,
    props.accountLabels,
    props.notes,
    props.showDataPoints,
  ],
  () => render(false),
  { deep: true },
);
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>

<template>
  <div class="usage-chart-wrap">
    <div ref="container" class="usage-chart" role="img" aria-label="AI usage over time" />
    <div
      v-if="regionTooltip"
      class="region-tooltip"
      :style="{ left: `${regionTooltip.x}px`, top: `${regionTooltip.y}px` }"
      v-html="regionTooltip.html"
    />
  </div>
</template>

<style scoped lang="scss">
.usage-chart-wrap {
  position: relative;
}
.usage-chart {
  width: 100%;
  min-height: 34rem;
}
.region-tooltip {
  position: absolute;
  transform: translate(12px, 12px);
  pointer-events: none;
  z-index: 10;
  max-width: 20rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: rgba(50, 50, 50, 0.9);
  color: #fff;
  font-size: 0.8125rem;
  line-height: 1.4;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
</style>

