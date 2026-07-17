<script setup lang="ts">
import { onMounted } from "vue";

onMounted(async () => {
  try {
    await fetch("/api/v1/sentry/sample-error");
  } catch {
    // The route intentionally fails when verification is enabled.
  }
  setTimeout(() => {
    throw new Error("frontend sample error for Sentry/Bugsink verification");
  }, 0);
});
</script>

<template>
  <main><h1>Sentry verification</h1><p>Backend and frontend sample errors were triggered.</p></main>
</template>

