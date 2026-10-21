<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NInput, NSwitch } from 'naive-ui'
import { Search, Terminal } from 'lucide-vue-next'
import { api, errorText } from '../api'
import { date } from '../format'
import type { Log } from '../types'

const props = defineProps<{ accountId: number }>()
const logs = ref<Log[]>([])
const error = ref('')
const search = ref('')
const follow = ref(true)
const viewport = ref<HTMLElement | null>(null)
const filtered = computed(() =>
  logs.value.filter((log) => log.message.toLowerCase().includes(search.value.toLowerCase())),
)
const controller = new AbortController()
let after = 0
let alive = true
let timer: ReturnType<typeof setTimeout> | undefined

async function refresh() {
  try {
    const result = await api<Log[]>(
      `/logs?account_id=${props.accountId}&source=yatori&after=${after}`,
      { signal: controller.signal },
    )
    if (!alive) return
    const known = new Set(logs.value.map((log) => log.id))
    logs.value = [...logs.value, ...result.filter((log) => !known.has(log.id))].slice(-2000)
    if (result.length) after = Math.max(after, ...result.map((log) => log.id))
    error.value = ''
    if (follow.value && result.length) {
      await nextTick()
      if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight
    }
  } catch (e) {
    if (alive) error.value = errorText(e)
  }
}
async function poll() {
  if (!document.hidden) await refresh()
  if (alive) timer = setTimeout(poll, 2000)
}
onMounted(poll)
onUnmounted(() => {
  alive = false
  controller.abort()
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <section class="panel account-log-panel" aria-labelledby="account-logs-heading">
    <div class="panel-heading account-log-heading">
      <div>
        <h2 id="account-logs-heading">Yatori 原始日志</h2>
        <p class="muted">该账号的 stdout / stderr 输出，每 2 秒更新；敏感凭据已脱敏。</p>
      </div>
      <RouterLink
        :to="{ path: '/logs', query: { account_id: accountId, source: 'yatori' } }"
        class="text-link small"
        >完整日志与导出</RouterLink
      >
    </div>
    <NAlert v-if="error" type="error"
      >{{ error }}<NButton text @click="refresh">重新连接</NButton></NAlert
    >
    <div class="account-log-tools">
      <NInput
        v-model:value="search"
        clearable
        placeholder="搜索当前日志"
        aria-label="搜索当前账号日志"
        ><template #prefix><Search :size="15" /></template
      ></NInput>
      <label class="account-log-follow"
        ><span>跟随最新</span
        ><NSwitch v-model:value="follow" size="small" aria-label="日志跟随最新"
      /></label>
    </div>
    <div ref="viewport" class="account-log-viewport" tabindex="0" aria-label="账号 Yatori 原始日志">
      <div v-if="!filtered.length" class="account-log-empty">
        <Terminal :size="25" /><span>{{ search ? '没有匹配的日志' : '等待账号的运行输出' }}</span>
      </div>
      <div v-for="log in filtered" :key="log.id" class="account-log-line">
        <time>{{ date(log.created_at) }}</time
        ><span class="account-log-level">{{ log.level.toUpperCase() }}</span
        ><span class="account-log-message">{{ log.message }}</span>
      </div>
    </div>
    <div class="log-footer">
      <span>最近 {{ logs.length }} 条已加载记录</span><span>按原始输出顺序</span>
    </div>
  </section>
</template>

<style scoped>
.account-log-heading {
  gap: 12px;
  flex-wrap: wrap;
}
.account-log-heading p {
  margin: 6px 0 0;
  font-size: 12px;
}
.account-log-tools {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
}
.account-log-tools .n-input {
  max-width: 360px;
}
.account-log-follow {
  display: flex;
  align-items: center;
  gap: 9px;
  white-space: nowrap;
}
.account-log-viewport {
  height: 340px;
  overflow: auto;
  padding: 12px 16px;
  background: #07101e;
  color: #d4dfed;
  font:
    12px/1.7 Consolas,
    'Microsoft YaHei',
    monospace;
}
.account-log-empty {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #94a3b8;
}
.account-log-line {
  display: grid;
  grid-template-columns: 145px 62px minmax(0, 1fr);
  gap: 10px;
  padding: 5px 0;
}
.account-log-line time,
.account-log-level {
  color: #9aafc9;
  font-size: 11px;
}
.account-log-message {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .account-log-tools {
    padding: 12px;
    gap: 10px;
  }
  .account-log-viewport {
    padding: 12px;
    height: 360px;
  }
  .account-log-line {
    grid-template-columns: 1fr auto;
    gap: 0 10px;
    padding: 7px 0;
    border-bottom: 1px solid #18263b;
  }
  .account-log-message {
    grid-column: 1 / -1;
  }
}
</style>
