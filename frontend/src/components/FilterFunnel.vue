<script setup lang="ts">
import Chip from "./Chip.vue";
import type { FunnelBranch, IconRef } from "../types";

defineProps<{
  tree: FunnelBranch[];
  activeServices: string[];
  activeProviders: string[];
  serviceIcons?: Record<string, IconRef>;
  providerIcons?: Record<string, IconRef>;
}>();

defineEmits<{
  "toggle-service": [service: string];
  "toggle-provider": [provider: string];
}>();
</script>

<template>
  <div class="filter-funnel" aria-label="Service and provider filters">
    <div v-for="branch in tree" :key="branch.service" class="funnel-branch">
      <Chip
        class="funnel-service"
        :label="branch.service"
        :active="activeServices.includes(branch.service)"
        :icon="serviceIcons?.[branch.service]"
        @click="$emit('toggle-service', branch.service)"
      />
      <div class="funnel-providers">
        <Chip
          v-for="provider in branch.providers"
          :key="provider"
          :label="provider"
          :active="activeProviders.includes(provider)"
          :icon="providerIcons?.[provider]"
          @click="$emit('toggle-provider', provider)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
// A minimal service -> providers funnel: each service chip on the left, its providers
// branching off to the right along a shared connector line, so the service/provider
// relationship reads visually instead of being two unrelated flat chip rows.
.filter-funnel {
  display: flex;
  flex-direction: column;
  gap: .6rem;
  width: 100%;
}

.funnel-branch {
  display: flex;
  align-items: center;
  gap: .75rem;
  flex-wrap: wrap;
}

.funnel-providers {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .4rem;
  padding-left: 1rem;
  border-left: 2px solid var(--border);
  min-height: 1.6rem;

  &::before {
    content: "";
    position: absolute;
    left: -2px;
    top: 50%;
    width: .75rem;
    height: 2px;
    background: var(--border);
  }
}
</style>
