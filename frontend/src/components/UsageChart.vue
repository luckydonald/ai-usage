<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, LegendScrollComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { axisTooltipHtml, chartOption, seriesDisplayName, seriesKey } from "../chart";
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
const closeButton = ref<HTMLButtonElement>();
const pinnedTooltipHtml = ref("");
const tooltipOpen = computed(() => pinnedTooltipHtml.value !== "");
let chart: echarts.ECharts | undefined;

function closePinnedTooltip(): void {
  pinnedTooltipHtml.value = "";
}

// The overlay is `position: fixed` over the whole viewport, so without this the page
// underneath keeps scrolling behind it — pausing on a pinned tooltip.
watch(tooltipOpen, (open) => {
  document.body.style.overflow = open ? "hidden" : "";
});

async function pinTooltip(offsetX: number, offsetY: number): Promise<void> {
  if (!chart || !chart.containPixel({ gridIndex: 0 }, [offsetX, offsetY])) return;
  const coordinate = chart.convertFromPixel({ gridIndex: 0 }, [offsetX, offsetY]);
  const atMs = Array.isArray(coordinate) ? coordinate[0] : undefined;
  if (typeof atMs !== "number") return;

  const html = axisTooltipHtml(props.series, [{ axisValue: atMs }], props.accountLabels, new Date(), props.notes);
  if (!html) return;
  chart.dispatchAction({ type: "hideTip" });
  pinnedTooltipHtml.value = html;
  await nextTick();
  closeButton.value?.focus();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") closePinnedTooltip();
}

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
    chart.getZr().on("click", (event) => {
      void pinTooltip(event.offsetX, event.offsetY);
    });
  }
}

function resize(): void {
  chart?.resize();
}

onMounted(() => {
  render(false);
  window.addEventListener("resize", resize);
  window.addEventListener("keydown", onKeydown);
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
  window.removeEventListener("keydown", onKeydown);
  if (tooltipOpen.value) document.body.style.overflow = "";
  chart?.dispose();
});
</script>

<template>
  <div ref="container" class="usage-chart" role="img" aria-label="AI usage over time" />
  <Teleport to="body">
    <div v-if="tooltipOpen" class="tooltip-overlay" role="presentation" @click.self="closePinnedTooltip">
      <section class="pinned-tooltip" role="dialog" aria-modal="true" aria-label="Usage details">
        <button ref="closeButton" class="pinned-tooltip-close" type="button" aria-label="Close usage details" @click="closePinnedTooltip">×</button>
        <div class="pinned-tooltip-content" v-html="pinnedTooltipHtml" />
      </section>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.usage-chart {
  width: 100%;
  min-height: 34rem;
}

.tooltip-overlay {
  position: fixed;
  z-index: 10;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgb(15 10 35 / 45%);
}

.pinned-tooltip {
  position: relative;
  width: min(32rem, 100%);
  max-height: min(75vh, 42rem);
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 1rem;
  background: var(--surface);
  color: var(--text);
  box-shadow: 0 1.5rem 4rem rgb(15 10 35 / 35%);
  line-height: 1.5;
}

.pinned-tooltip-close {
  position: absolute;
  top: .6rem;
  right: .6rem;
  width: 2rem;
  height: 2rem;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface-muted);
  color: var(--text);
  cursor: pointer;
  font-size: 1.35rem;
  line-height: 1;

  &:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
  }
}

.pinned-tooltip-content {
  max-height: min(75vh, 42rem);
  overflow: auto;
  padding: 1.25rem 3rem 1.25rem 1.25rem;
}

.pinned-tooltip-content :deep(a) {
  color: var(--color-primary);
}
</style>
