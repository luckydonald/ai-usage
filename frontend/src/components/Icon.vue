<script setup lang="ts">
withDefaults(
  defineProps<{
    icon: string
    source?: string
    family?: string
    version?: string
  }>(),
  {
    source: "fontawesome-free-pack",
    family: "brands",
    version: "latest",
  },
)
</script>

<template>
  <span class="icon-badge">
    <img :src="`/img/icons/${source}/${version}/${family}/${icon}.svg`" :alt="icon" class="icon" />
  </span>
</template>
