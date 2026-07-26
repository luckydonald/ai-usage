<script setup lang="ts">
import Icon from "./Icon.vue";
import type { IconRef } from "../types";

defineProps<{
  label: string
  active: boolean
  icon?: IconRef
  title?: string
}>();

defineEmits<{
  click: []
}>();
</script>

<template>
  <button type="button" class="chip" :class="{ active }" :title="title" @click="$emit('click')">
    <Icon v-if="icon" v-bind="icon" /> {{ label }}
  </button>
</template>
