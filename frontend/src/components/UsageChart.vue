<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, LegendScrollComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { chartOption, type MarkAreaHoverEvent, regionTooltipHtml, seriesDisplayName, seriesKey } from "../chart";
import type { GraphSeries, NoteRange } from "../types";

echarts.use([
  LineChart,
  GridComponent,
  LegendComponent,
  LegendScrollComponent,
  TooltipComponent,
  MarkAreaComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

// No echarts "dark" theme registration here on purpose: importing it side-effect-style
// (`echarts/theme/dark`) is a raw UMD file whose CJS/global-detection branches don't behave
// the same under Vitest/happy-dom as in a real browser and hung the whole app-mount test.
// chartOption() already themes every color (background, text, tooltip, gridlines, axis
// labels) explicitly off the `dark` prop, so no built-in theme is needed.

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
  chart ??= echarts.init(container.value);
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
    // axis-trigger slice. Render that content ourselves via a manually-positioned div.
    // Tried `dispatchAction({type:"hideTip"})`, `setOption({tooltip:{show:false}})`, and
    // directly setting the built-in tooltip DOM node's `style.display` from JS — all three
    // raced with ECharts' own internal axis-trigger show/reposition logic (it rewrites that
    // node's whole `style.cssText`, including `display`, on every mousemove) and kept losing.
    // A CSS rule with `!important` in the template below can't lose that race — it's not a
    // per-event JS mutation, so there's nothing for ECharts' own inline-style writes to race
    // against. Toggling this class is the only thing this handler does now.
    chart.on("mouseover", { componentType: "markArea" }, (raw: unknown) => {
      const params = raw as MarkAreaHoverEvent & { event?: { offsetX: number; offsetY: number } };
      const html = regionTooltipHtml(props.series, params, new Date(), props.accountLabels, props.notes);
      if (html && params.event) {
        regionTooltip.value = { html, x: params.event.offsetX, y: params.event.offsetY };
      }
    });
    chart.on("mouseout", { componentType: "markArea" }, () => {
      regionTooltip.value = null;
    });
    chart.getZr().on("mousemove", (raw: unknown) => {
      if (!regionTooltip.value) return;
      const event = raw as { offsetX: number; offsetY: number };
      regionTooltip.value = { ...regionTooltip.value, x: event.offsetX, y: event.offsetY };
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
// Dark mode is no longer an echarts init-time "theme" (see the comment above `echarts.use`),
// just a set of colors in chartOption() — a plain merge update is enough, no full recreate.
watch(
  () => [
    props.series,
    props.dark,
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
  <div class="usage-chart-wrap" :class="{ 'hiding-native-tooltip': !!regionTooltip }">
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
// The canvas ECharts renders into is also wrapped in a plain, un-styled `div` right here —
// `:not(:has(canvas))` is what tells the built-in tooltip's wrapper apart from it.
// `:deep()` is required: Vue's scoped-CSS attribute-scoping only tags elements that exist in
// this component's own template, and ECharts injects the tooltip div at runtime — a plain
// scoped selector silently never matches anything on it.
.usage-chart-wrap.hiding-native-tooltip .usage-chart {
  :deep(> div:not(:has(canvas))) {
    display: none !important;
  }
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

