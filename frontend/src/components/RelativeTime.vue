<script setup lang="ts">
import { computed } from "vue";

import { formatRelative } from "../time";

const props = defineProps<{
  at: Date;
  now?: Date;
}>();

const absolute = computed(() => props.at.toLocaleString());
const relative = computed(() => formatRelative(props.at, props.now ?? new Date()));
</script>

<template>
  <span :title="absolute">{{ relative }}</span>
</template>
