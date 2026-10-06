<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const hallId = ref(1)
const result = ref<any>(null)
const loading = ref(false)
const error = ref('')

async function check() {
  loading.value = true
  error.value = ''
  try {
    // 只读校验入口：只读取漂移分码，不改历史方案、不插新方案
    result.value = await api(`/seating/validate?hall_id=${hallId.value}`)
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}
onMounted(check)
</script>

<template>
  <h1>校验漂移</h1>
  <p class="sub">只读校验 · 不修改历史方案正文、不新增方案；间距类与同卷类漂移分码互斥</p>
  <div class="card">
    <label class="muted">考室 ID：
      <input v-model.number="hallId" type="number" min="1" style="width:90px" />
    </label>
    <button class="btn" :disabled="loading" @click="check" style="margin-left:0.6rem">
      {{ loading ? '校验中…' : '只读校验' }}
    </button>
  </div>

  <div v-if="error" class="card" style="color:var(--hs-bad)">{{ error }}</div>

  <div v-else-if="result" class="card">
    <table>
      <tbody>
        <tr><th>方案条数</th><td>{{ result.plan_count }}</td></tr>
        <tr><th>生效方案</th><td>{{ result.active_plan_id ?? '—' }}</td></tr>
        <tr><th>漂移分码</th>
          <td>
            <span v-if="(result.drift_codes || []).length === 0" class="badge badge-ok">无漂移 · 空结果</span>
            <span v-for="code in result.drift_codes" :key="code" class="badge badge-warn" style="margin-right:0.35rem">{{ code }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="muted" style="margin-bottom:0">现网最小距 {{ result.current_min_dist }} · 生成时最小距 {{ result.generated_min_dist ?? '—' }}</p>
  </div>
</template>
