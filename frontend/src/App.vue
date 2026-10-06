<script setup lang="ts">
const tabs = [
  { to: '/halls', label: '考室' },
  { to: '/candidates', label: '考生名册' },
  { to: '/papers', label: '试卷套' },
  { to: '/map', label: '排座图' },
  { to: '/violations', label: '违规与漂移' },
  { to: '/stats', label: '统计' },
]
</script>

<template>
  <div class="hs-exam">
    <header class="hs-paper-tabs">
      <div class="hs-brand">HALLSPAN · 考场排座</div>
      <nav class="hs-tabs">
        <router-link v-for="t in tabs" :key="t.to" :to="t.to">{{ t.label }}</router-link>
      </nav>
    </header>
    <main class="hs-workspace">
      <router-view />
    </main>
  </div>
</template>
