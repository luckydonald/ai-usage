<script setup lang="ts">
defineProps<{
  label: string;
  color?: string;
}>();
</script>

<template>
  <span class="badge" :style="color ? { background: color } : undefined">{{ label }}</span>
</template>

<style scoped lang="scss">
.badge {
  display: inline-block;
  padding: .1rem .55rem;
  margin: .1rem .35rem .1rem 0;
  border-radius: 999px;
  background: var(--surface-muted);
  color: #fff;
  font-size: .85em;
  line-height: 1.5;
  white-space: nowrap;
}
</style>
