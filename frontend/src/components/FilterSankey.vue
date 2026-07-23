<script setup lang="ts">
import { SankeyChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { buildSankeyData } from "../sankey";
import type { FunnelBranch, IconRef } from "../types";

echarts.use([SankeyChart, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  tree: FunnelBranch[];
  activeServices: string[];
  activeProviders: string[];
  activeAccounts: string[];
  activeMetrics: string[];
  dark: boolean;
  serviceIcons?: Record<string, IconRef>;
  providerIcons?: Record<string, IconRef>;
}>();

const emit = defineEmits<{
  "toggle-service": [service: string];
  "toggle-provider": [provider: string];
  "toggle-account": [accountId: string];
  "toggle-metric": [metricKey: string];
}>();

const container = ref<HTMLDivElement>();
let chart: echarts.ECharts | undefined;

interface SankeyClickParams {
  dataType?: string;
  data?: { kind?: string; refId?: string };
}

function onNodeClick(raw: unknown): void {
  const params = raw as SankeyClickParams;
  if (params.dataType !== "node" || !params.data?.kind || params.data.refId === undefined) return;
  const { kind, refId } = params.data;
  if (kind === "service") emit("toggle-service", refId);
  else if (kind === "provider") emit("toggle-provider", refId);
  else if (kind === "account") emit("toggle-account", refId);
  else if (kind === "metric") emit("toggle-metric", refId);
}

function render(): void {
  if (!container.value) return;
  const isNew = !chart;
  chart ??= echarts.init(container.value);
  const { nodes, links } = buildSankeyData(
    props.tree,
    { services: props.activeServices, providers: props.activeProviders, accounts: props.activeAccounts, metrics: props.activeMetrics },
    props.dark,
    props.serviceIcons,
    props.providerIcons,
  );
  chart.setOption({
    series: [
      {
        type: "sankey",
        orient: "horizontal",
        nodeAlign: "justify",
        emphasis: { focus: "adjacency" },
        label: { show: true },
        data: nodes,
        links,
      },
    ],
  });
  if (isNew) chart.on("click", onNodeClick);
}

function resize(): void {
  chart?.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", resize);
});

watch(
  () => [
    props.tree,
    props.activeServices,
    props.activeProviders,
    props.activeAccounts,
    props.activeMetrics,
    props.dark,
    props.serviceIcons,
    props.providerIcons,
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
  <div ref="container" class="filter-sankey" role="img" aria-label="Service, provider, account, and metric filters" />
</template>

<style scoped lang="scss">
.filter-sankey {
  width: 100%;
  min-height: 16rem;
}
</style>
