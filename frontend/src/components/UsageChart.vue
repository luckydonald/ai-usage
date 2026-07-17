<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { chartOption } from "../chart";
import type { GraphSeries } from "../types";

const props = defineProps<{ series: GraphSeries[]; dark: boolean; exhaustedColor: string }>();
const container = ref<HTMLDivElement>();
let chart: echarts.ECharts | undefined;

function render(): void {
  if (!container.value) return;
  chart ??= echarts.init(container.value, props.dark ? "dark" : undefined);
  chart.setOption(chartOption(props.series, props.dark, props.exhaustedColor), true);
}

function resize(): void {
  chart?.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", resize);
});
watch(() => [props.series, props.dark, props.exhaustedColor], () => {
  chart?.dispose();
  chart = undefined;
  render();
}, { deep: true });
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

