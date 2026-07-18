<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { chartOption, seriesDisplayName, seriesKey } from "../chart";
import type { GraphSeries } from "../types";

const props = defineProps<{
  series: GraphSeries[];
  dark: boolean;
  exhaustedColor: string;
  hiddenSeriesKeys: string[];
  rangeStart: Date;
  rangeEnd: Date;
}>();
const emit = defineEmits<{ (event: "toggle-series", key: string, visible: boolean): void }>();
const container = ref<HTMLDivElement>();
let chart: echarts.ECharts | undefined;

function legendSelected(): Record<string, boolean> {
  const selected: Record<string, boolean> = {};
  for (const item of props.series) {
    selected[seriesDisplayName(item)] = !props.hiddenSeriesKeys.includes(seriesKey(item));
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
    }),
    recreate || isNew,
  );
  if (isNew) {
    chart.on("legendselectchanged", (raw: unknown) => {
      const params = raw as { name: string; selected: Record<string, boolean> };
      const item = props.series.find((entry) => seriesDisplayName(entry) === params.name);
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
watch(() => props.dark, () => render(true));
watch(
  () => [props.series, props.exhaustedColor, props.hiddenSeriesKeys, props.rangeStart, props.rangeEnd],
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

