<script setup lang="ts">
const tabs = [
  { to: '/halls', label: '考室' },
  { to: '/candidates', label: '考生名册' },
  { to: '/papers', label: '试卷套' },
  { to: '/map', label: '排座图' },
  { to: '/violations', label: '校验漂移' },
  { to: '/stats', label: '统计' },
]
</script>

<template>
  <div class="hs-exam">
    <header class="hs-paper-tabs">
      <div class="hs-brand">HALLSPAN · 考场排座</div>
      <nav class="hs-tabs">
        <RouterLink v-for="t in tabs" :key="t.to" :to="t.to">{{ t.label }}</RouterLink>
      </nav>
    </header>
    <main class="hs-workspace">
      <RouterView />
    </main>
  </div>
</template>
