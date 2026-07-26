<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    name: string
    set?: string
    pack?: string
    version?: string
    color?: string
  }>(),
  {
    pack: "fontawesome-free-pack",
    set: "brands",
    version: "latest",
  },
)

const iconUrl = computed(() => `/img/icons/${props.pack}/${props.version}/${props.set}/${props.name}.svg`);
</script>

<template>
  <span class="icon-badge">
    <span
      v-if="color"
      class="icon icon-tinted"
      :style="{ backgroundColor: color, maskImage: `url(${iconUrl})`, WebkitMaskImage: `url(${iconUrl})` }"
      role="img"
      :aria-label="name"
    />
    <img v-else :src="iconUrl" :alt="name" class="icon" />
  </span>
</template>

<style scoped>
.icon-tinted {
  display: inline-block;
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-position: center;
}
</style>
