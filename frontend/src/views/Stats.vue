<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const plans = ref<any[]>([])
const report = ref<any>(null)

onMounted(async () => {
  plans.value = await api('/seating/plans?hall_id=1')
  report.value = await api('/seating/validate?hall_id=1')
})

const active = computed(() => plans.value.filter(p => !p.voided))
const latest = computed(() => active.value[active.value.length - 1])
const stats = computed(() => latest.value?.stats || {})
</script>

<template>
  <h1>统计</h1>
  <p class="sub">方案只增不改 · 校验只读 · 漂移分码互斥</p>
  <div style="display:flex;gap:0.85rem;flex-wrap:wrap">
    <div class="card" style="min-width:140px">
      <div class="muted">方案行数(含作废)</div>
      <div class="stat">{{ plans.length }}</div>
    </div>
    <div class="card" style="min-width:140px">
      <div class="muted">有效方案</div>
      <div class="stat">{{ active.length }}</div>
    </div>
    <div class="card" style="min-width:140px">
      <div class="muted">已入座 / 容量</div>
      <div class="stat">{{ stats.seated ?? 0 }} / {{ stats.capacity ?? 0 }}</div>
    </div>
    <div class="card" style="min-width:140px">
      <div class="muted">未排入</div>
      <div class="stat">{{ stats.unplaced ?? 0 }}</div>
    </div>
    <div class="card" style="min-width:140px">
      <div class="muted">违规</div>
      <div class="stat">{{ stats.violations ?? 0 }}</div>
    </div>
    <div class="card" style="min-width:140px">
      <div class="muted">漂移分码</div>
      <div class="stat">{{ report?.drifts?.length ?? 0 }}</div>
    </div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>方案</th><th>生成时间</th><th>状态</th><th>入座</th><th>违规</th></tr></thead>
      <tbody>
        <tr v-for="p in plans" :key="p.id">
          <td>#{{ p.id }}</td>
          <td>{{ p.created_at }}</td>
          <td>
            <span class="badge" :class="p.voided ? 'badge-bad' : 'badge-ok'">
              {{ p.voided ? '已作废' : '有效' }}
            </span>
          </td>
          <td>{{ p.stats?.seated ?? 0 }}</td>
          <td>{{ p.stats?.violations ?? 0 }}</td>
        </tr>
        <tr v-if="!plans.length"><td colspan="5" class="muted">暂无方案</td></tr>
      </tbody>
    </table>
  </div>
</template>
