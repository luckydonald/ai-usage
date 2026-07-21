<script setup lang="ts">
withDefaults(
  defineProps<{
    name: string
    set?: string
    pack?: string
    version?: string
  }>(),
  {
    pack: "fontawesome-free-pack",
    set: "brands",
    version: "latest",
  },
)
</script>

<template>
  <span class="icon-badge">
    <img :src="`/img/icons/${pack}/${version}/${set}/${name}.svg`" :alt="name" class="icon" />
  </span>
</template>
