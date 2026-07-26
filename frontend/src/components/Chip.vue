<script setup lang="ts">
import Icon from "./Icon.vue";
import type { IconRef } from "../types";

defineProps<{
  label: string
  active: boolean
  icon?: IconRef
  title?: string
  iconOnly?: boolean
}>();

defineEmits<{
  click: []
}>();
</script>

<template>
  <button
    type="button"
    class="chip"
    :class="{ active }"
    :title="title"
    :aria-label="iconOnly ? label : undefined"
    @click="$emit('click')"
  >
    <Icon v-if="icon" v-bind="icon" /><template v-if="!iconOnly"> {{ label }}</template>
  </button>
</template>
