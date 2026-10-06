<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const hallId = ref(1)
const plans = ref<any[]>([])
const validation = ref<any>(null)

async function load() {
  const [p, v] = await Promise.all([
    api(`/seating/plans?hall_id=${hallId.value}`),
    api(`/seating/validate?hall_id=${hallId.value}`),
  ])
  plans.value = p
  validation.value = v
}
onMounted(load)
</script>

<template>
  <h1>统计</h1>
  <p class="sub">方案台账（追加式）与只读校验结果汇总</p>
  <div v-if="validation" style="display:flex;gap:0.85rem;flex-wrap:wrap;margin-bottom:1rem">
    <div class="card" style="min-width:150px;margin-bottom:0">
      <div class="stat">{{ validation.plan_count }}</div>
      <div class="muted">方案条数（含作废）</div>
    </div>
    <div class="card" style="min-width:150px;margin-bottom:0">
      <div class="stat">{{ validation.active_plan_id ?? '—' }}</div>
      <div class="muted">最新生效方案</div>
    </div>
    <div class="card" style="min-width:150px;margin-bottom:0">
      <div class="stat">{{ (validation.drift_codes || []).length ? validation.drift_codes.join(' / ') : '无漂移' }}</div>
      <div class="muted">漂移分码（间距/同卷互斥）</div>
    </div>
  </div>

  <div class="card">
    <table>
      <thead>
        <tr><th>方案 ID</th><th>状态</th><th>生成时最小距</th><th>创建时间</th><th>作废时间</th></tr>
      </thead>
      <tbody>
        <tr v-for="p in plans" :key="p.plan_id">
          <td>{{ p.plan_id }}</td>
          <td>
            <span class="badge" :class="p.status === 'active' ? 'badge-ok' : 'badge-bad'">{{ p.status }}</span>
          </td>
          <td>{{ p.gen_min_dist }}</td>
          <td>{{ p.created_at }}</td>
          <td>{{ p.voided_at ?? '—' }}</td>
        </tr>
        <tr v-if="plans.length === 0"><td colspan="5" class="muted">暂无方案（校验固定空结果）</td></tr>
      </tbody>
    </table>
  </div>
</template>
