<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const violations = ref<any[]>([])
const report = ref<any>(null)

onMounted(async () => {
  const v = await api('/seating/violations?hall_id=1')
  violations.value = v.violations || []
  report.value = await api('/seating/validate?hall_id=1')
})

const DRIFT_LABELS: Record<string, string> = {
  MIN_DIST_DRIFT: '间距漂移',
  SAME_PAPER_DRIFT: '同卷漂移',
}
function driftLabel(code: string) {
  return DRIFT_LABELS[code] || code
}
</script>

<template>
  <h1>违规与漂移</h1>
  <p class="sub">违规来自最新有效方案 · 漂移分码来自只读校验(不改历史行)</p>

  <div class="card">
    <h2 style="margin-top:0">漂移分码</h2>
    <table>
      <thead><tr><th>方案</th><th>分码</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(d, i) in report?.drifts || []" :key="i">
          <td>#{{ d.plan_id }}</td>
          <td>
            <span class="badge" :class="d.code === 'MIN_DIST_DRIFT' ? 'badge-warn' : 'badge-bad'">
              {{ driftLabel(d.code) }} · {{ d.code }}
            </span>
          </td>
          <td>{{ d.detail }}</td>
        </tr>
        <tr v-if="!(report?.drifts || []).length">
          <td colspan="3" class="muted">无漂移:现网参数与生成快照一致</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2 style="margin-top:0">违规清单</h2>
    <table>
      <thead><tr><th>类型</th><th>考生 A</th><th>考生 B</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(v, i) in violations" :key="i">
          <td>
            <span class="badge" :class="v.kind === 'distance' ? 'badge-warn' : 'badge-bad'">
              {{ v.kind === 'distance' ? '间距' : '同卷相邻' }}
            </span>
          </td>
          <td>{{ v.a_id }}</td>
          <td>{{ v.b_id }}</td>
          <td>{{ v.detail }}</td>
        </tr>
        <tr v-if="!violations.length"><td colspan="4" class="muted">无违规</td></tr>
      </tbody>
    </table>
  </div>
</template>
