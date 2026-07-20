<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, LegendScrollComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { chartOption, seriesDisplayName, seriesKey } from "../chart";
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
  <div ref="container" class="usage-chart" role="img" aria-label="AI usage over time" />
</template>

<style scoped lang="scss">
.usage-chart {
  width: 100%;
  min-height: 34rem;
}
</style>
