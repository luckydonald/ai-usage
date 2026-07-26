<script setup lang="ts">
import { SankeyChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import { buildSankeyData, type SankeyNodeDatum } from "../sankey";
import type { IconRef, SankeyService } from "../types";
import Chip from "./Chip.vue";

echarts.use([SankeyChart, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  tree: SankeyService[];
  activeAccounts: string[];
  activeMetrics: string[];
  dark: boolean;
  serviceIcons?: Record<string, IconRef>;
  metricIcons?: Record<string, IconRef>;
}>();

const emit = defineEmits<{
  "toggle-service": [serviceId: string];
  "toggle-account": [accountId: string];
  "toggle-organization": [organizationId: string];
  "toggle-parser": [configId: string];
  "toggle-metric": [metricKey: string];
}>();

const container = ref<HTMLDivElement>();
let chart: echarts.ECharts | undefined;
const nodes = ref<SankeyNodeDatum[]>([]);
// Node pixel positions, keyed by node id — the overlaid `Chip` (a real DOM button, not an
// echarts label) is what actually shows the icon+text and takes clicks, so it needs each node's
// rendered position. echarts doesn't expose a public coordinate API for Sankey (no coordinate
// system like a grid/geo to `convertToPixel` against), so this reads the layout the Sankey
// renderer itself computed, the same technique used elsewhere for overlaying DOM on canvas charts.
const positions = reactive<Record<string, { left: number; top: number }>>({});

function isActive(node: SankeyNodeDatum): boolean {
  return node.active;
}

function chipStyle(node: SankeyNodeDatum): { left: string; top: string } | { display: string } {
  const position = positions[node.name];
  return position ? { left: `${position.left}px`, top: `${position.top}px` } : { display: "none" };
}

function toggle(node: SankeyNodeDatum): void {
  if (node.kind === "service") emit("toggle-service", node.refId);
  else if (node.kind === "account") emit("toggle-account", node.refId);
  else if (node.kind === "organization") emit("toggle-organization", node.refId);
  else if (node.kind === "parser") emit("toggle-parser", node.refId);
  else emit("toggle-metric", node.refId);
}

interface SankeyItemLayout {
  x: number;
  y: number;
  dx: number;
  dy: number;
}

// `getModel()` is a private ECharts API in the type defs, but a real, stable method on the
// instance at runtime — there is no public alternative for reading a Sankey series' computed
// node layout.
function readItemLayout(index: number): SankeyItemLayout | undefined {
  const anyChart = chart as unknown as {
    getModel?: () => { getSeriesByIndex: (index: number) => { getData: () => { getItemLayout: (index: number) => SankeyItemLayout | undefined } } | undefined };
  };
  return anyChart.getModel?.()?.getSeriesByIndex(0)?.getData().getItemLayout(index);
}

function updatePositions(): void {
  if (!chart) return;
  for (const key of Object.keys(positions)) delete positions[key];
  nodes.value.forEach((node, index) => {
    const layout = readItemLayout(index);
    if (!layout) return;
    positions[node.name] = { left: layout.x + layout.dx + 8, top: layout.y + layout.dy / 2 };
  });
}

function render(): void {
  if (!container.value) return;
  chart ??= echarts.init(container.value);
  const built = buildSankeyData(
    props.tree,
    props.activeAccounts,
    props.activeMetrics,
    props.dark,
    props.serviceIcons,
    props.metricIcons,
  );
  nodes.value = built.nodes;
  chart.setOption({
    series: [
      {
        type: "sankey",
        orient: "horizontal",
        nodeAlign: "justify",
        emphasis: { focus: "adjacency" },
        label: { show: false },
        data: built.nodes,
        links: built.links,
      },
    ],
  });
  void nextTick(() => updatePositions());
}

function resize(): void {
  chart?.resize();
  void nextTick(() => updatePositions());
}

onMounted(() => {
  render();
  window.addEventListener("resize", resize);
});

watch(
  () => [
    props.tree,
    props.activeAccounts,
    props.activeMetrics,
    props.dark,
    props.serviceIcons,
    props.metricIcons,
  ],
  () => render(),
  { deep: true },
);

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>

<template>
  <div class="filter-sankey">
    <div ref="container" class="filter-sankey-canvas" role="img" aria-label="Service, account, organization, parser, and metric filters" />
    <div class="filter-sankey-overlay">
      <Chip
        v-for="node in nodes"
        :key="node.name"
        class="filter-sankey-chip"
        :style="chipStyle(node)"
        :label="node.displayName"
        :icon="node.icon"
        :title="node.title"
        :icon-only="node.kind === 'service'"
        :active="isActive(node)"
        @click="toggle(node)"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.filter-sankey {
  position: relative;
  width: 100%;
  min-height: 16rem;
}

.filter-sankey-canvas {
  width: 100%;
  height: 100%;
  min-height: 16rem;
}

.filter-sankey-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.filter-sankey-chip {
  position: absolute;
  transform: translateY(-50%);
  pointer-events: auto;
  white-space: nowrap;
}
</style>
