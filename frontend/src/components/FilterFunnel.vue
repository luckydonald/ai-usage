<script setup lang="ts">
import Chip from "./Chip.vue";
import type { FunnelBranch, IconRef } from "../types";

defineProps<{
  tree: FunnelBranch[];
  activeServices: string[];
  activeProviders: string[];
  activeAccounts: string[];
  activeMetrics: string[];
  serviceIcons?: Record<string, IconRef>;
  providerIcons?: Record<string, IconRef>;
}>();

defineEmits<{
  "toggle-service": [service: string];
  "toggle-provider": [provider: string];
  "toggle-account": [accountId: string];
  "toggle-metric": [metricKey: string];
}>();
</script>

<template>
  <div class="filter-funnel" aria-label="Service, provider, account, and metric filters">
    <div v-for="branch in tree" :key="branch.service" class="funnel-branch">
      <Chip
        :label="branch.service"
        :active="activeServices.includes(branch.service)"
        :icon="serviceIcons?.[branch.service]"
        @click="$emit('toggle-service', branch.service)"
      />
      <div class="funnel-branches">
        <div v-for="providerNode in branch.providers" :key="providerNode.provider" class="funnel-branch">
          <Chip
            :label="providerNode.provider"
            :active="activeProviders.includes(providerNode.provider)"
            :icon="providerIcons?.[providerNode.provider]"
            @click="$emit('toggle-provider', providerNode.provider)"
          />
          <div class="funnel-branches">
            <div v-for="accountNode in providerNode.accounts" :key="accountNode.id" class="funnel-branch">
              <Chip
                :label="accountNode.label"
                :active="activeAccounts.includes(accountNode.id)"
                @click="$emit('toggle-account', accountNode.id)"
              />
              <div class="funnel-leaves">
                <Chip
                  v-for="metric in accountNode.metrics"
                  :key="metric.key"
                  :label="metric.name"
                  :active="activeMetrics.includes(metric.key)"
                  @click="$emit('toggle-metric', metric.key)"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
// A service -> provider -> account -> metric funnel: each level's chip sits to the left of
// its children, connected by a shared guide line, so the full filter hierarchy reads as one
// diagram instead of four unrelated flat chip rows.
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

// Holds one or more child `.funnel-branch` rows (provider/account levels), stacked vertically.
.funnel-branches {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: .5rem;
  padding-left: 1rem;
  border-left: 2px solid var(--border);

  &::before {
    content: "";
    position: absolute;
    left: -2px;
    top: .8rem;
    width: .75rem;
    height: 2px;
    background: var(--border);
  }
}

// Holds the terminal metric chips of an account, wrapped horizontally since there are no
// further children beneath them.
.funnel-leaves {
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
