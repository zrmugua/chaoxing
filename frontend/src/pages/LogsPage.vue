<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NInput, NInputNumber, NSelect, NSwitch, useMessage } from 'naive-ui'
import { ArrowDownToLine, Pause, Play, RefreshCw, Search, Terminal } from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import { useResource } from '../composables/useResource'
import { api, errorText } from '../api'
import { date } from '../format'
import type { Account, Log } from '../types'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const logs = ref<Log[]>([])
const accounts = useResource<Account[]>('/accounts', [])
const accountOptions = computed(() =>
  accounts.data.value.map((account) => ({ label: account.label, value: account.id })),
)
const loading = ref(false)
const error = ref('')
const paused = ref(false)
const colorLog = ref(true)
onMounted(async () => {
  try {
    colorLog.value = (await api<{ color_log: boolean }>('/settings')).color_log
  } catch {
    /* Refresh reports connection errors. */
  }
})
const follow = ref(true)
const level = ref<string | null>(null)
const search = ref('')
const taskId = ref<number | null>(Number(route.query.task_id) || null)
const accountId = ref<number | null>(Number(route.query.account_id) || null)
function logSource(value: unknown): 'yatori' | 'console' | 'all' {
  return value === 'console' || value === 'all' ? value : 'yatori'
}
const source = ref(logSource(route.query.source))
const sources = [
  { label: 'Yatori 原始日志', value: 'yatori' },
  { label: '管理台日志', value: 'console' },
  { label: '全部来源', value: 'all' },
]
const viewport = ref<HTMLElement | null>(null)
let after = 0
let generation = 0
let timer: ReturnType<typeof setInterval> | undefined
let inFlight = false
let alive = true
const levels = [
  { label: 'INFO · 信息', value: 'INFO' },
  { label: 'WARNING · 警告', value: 'WARNING' },
  { label: 'ERROR · 错误', value: 'ERROR' },
  { label: 'DEBUG · 调试', value: 'DEBUG' },
]
const filtered = computed(() =>
  logs.value.filter(
    (log) =>
      (!level.value || log.level.toUpperCase() === level.value) &&
      log.message.toLowerCase().includes(search.value.toLowerCase()),
  ),
)
async function scrollBottom() {
  await nextTick()
  if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight
}
async function refresh() {
  if (inFlight) return
  const current = generation
  inFlight = true
  loading.value = true
  try {
    const query = new URLSearchParams({ after: String(after) })
    if (taskId.value) query.set('task_id', String(taskId.value))
    if (accountId.value) query.set('account_id', String(accountId.value))
    if (source.value !== 'all') query.set('source', source.value)
    const result = await api<Log[]>(`/logs?${query}`)
    if (!alive || current !== generation) return
    const known = new Set(logs.value.map((log) => log.id))
    logs.value = [...logs.value, ...result.filter((log) => !known.has(log.id))].slice(-2000)
    if (result.length) after = Math.max(after, ...result.map((log) => log.id))
    error.value = ''
    if (follow.value) await scrollBottom()
  } catch (e) {
    if (alive && current === generation) error.value = errorText(e)
  } finally {
    inFlight = false
    if (alive) loading.value = false
    if (alive && current !== generation) void refresh()
  }
}
function exportLogs() {
  if (!filtered.value.length) {
    message.info('当前没有可导出的日志')
    return
  }
  const blob = new Blob(
    [
      filtered.value
        .map(
          (log) =>
            `${date(log.created_at)} [${log.level}] [${log.source === 'yatori' ? 'Yatori' : '管理台'}] ${log.account_id ? `[${log.account_label || `账号 #${log.account_id}`}] ` : ''}${log.task_id ? `[任务 #${log.task_id}] ` : ''}${log.message}`,
        )
        .join('\n'),
    ],
    { type: 'text/plain;charset=utf-8' },
  )
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `chaoxing-logs-${new Date().toISOString().slice(0, 10)}.txt`
  a.click()
  URL.revokeObjectURL(url)
}
watch([taskId, accountId, source], () => {
  const query = { ...route.query }
  if (taskId.value) query.task_id = String(taskId.value)
  else delete query.task_id
  if (accountId.value) query.account_id = String(accountId.value)
  else delete query.account_id
  query.source = source.value
  void router.replace({ query })
  generation++
  logs.value = []
  after = 0
  void refresh()
})
watch(
  () => [route.query.task_id, route.query.account_id, route.query.source],
  ([task, account, origin]) => {
    taskId.value = Number(task) || null
    accountId.value = Number(account) || null
    source.value = logSource(origin)
  },
)
watch(follow, (value) => {
  if (value) void scrollBottom()
})
onMounted(() => {
  void refresh()
  timer = setInterval(() => {
    if (!paused.value && !document.hidden) void refresh()
  }, 2000)
})
onUnmounted(() => {
  alive = false
  if (timer) clearInterval(timer)
})
</script>

<template>
  <PageHeading title="运行日志" description="查看 Yatori 控制台原文，按账号、任务或来源筛选。"
    ><NButton @click="exportLogs"
      ><template #icon><ArrowDownToLine :size="15" /></template>导出当前日志</NButton
    ><NButton :type="paused ? 'primary' : 'default'" @click="paused = !paused"
      ><template #icon><Play v-if="paused" :size="15" /><Pause v-else :size="15" /></template
      >{{ paused ? '继续更新' : '暂停更新' }}</NButton
    ></PageHeading
  ><NAlert v-if="error || accounts.error.value" type="error" class="mb-20">{{
    error || accounts.error.value
  }}</NAlert>
  <p class="log-description">
    Yatori 日志保留控制台输出原文，密码、Cookie 和令牌会脱敏。账号任务运行后持续更新。
  </p>
  <section class="panel log-panel">
    <div class="log-toolbar">
      <div class="filter-inputs">
        <NSelect
          v-model:value="accountId"
          :options="accountOptions"
          filterable
          clearable
          placeholder="全部学习通账号"
          aria-label="筛选学习通账号"
          style="width: 200px"
        /><NSelect
          v-model:value="source"
          :options="sources"
          aria-label="筛选日志来源"
          style="width: 180px"
        />
        <NInputNumber
          v-model:value="taskId"
          :min="1"
          :show-button="false"
          clearable
          placeholder="全部任务 · 输入 ID"
          aria-label="筛选任务 ID"
          style="width: 175px"
        /><NSelect
          v-model:value="level"
          :options="levels"
          clearable
          placeholder="全部级别"
          style="width: 160px"
        /><NInput v-model:value="search" placeholder="搜索日志内容" clearable class="log-search"
          ><template #prefix><Search :size="15" /></template
        ></NInput>
      </div>
      <div class="log-follow">
        <span>自动滚动</span><NSwitch v-model:value="follow" size="small" /><NButton
          quaternary
          circle
          :loading="loading"
          aria-label="刷新日志"
          @click="refresh"
          ><RefreshCw :size="16"
        /></NButton>
      </div>
    </div>
    <div class="terminal-top">
      <div>
        <span class="status-dot" :class="{ online: !paused }" />{{
          paused ? '更新已暂停' : '实时日志'
        }}<span class="terminal-dot">·</span>每 2 秒同步
      </div>
      <span>{{ filtered.length }} 条记录</span>
    </div>
    <div ref="viewport" class="log-viewport" tabindex="0" aria-label="运行日志">
      <div v-if="!filtered.length" class="log-empty">
        <Terminal :size="32" :stroke-width="1.2" /><span>{{
          search || level
            ? '当前筛选下没有日志'
            : source === 'yatori'
              ? '等待 Yatori 控制台输出'
              : '等待新的运行日志'
        }}</span
        ><small>{{
          taskId
            ? `正在查看任务 #${taskId} 的记录`
            : accountId
              ? '该账号的执行日志将在这里显示'
              : '运行账号任务后，日志将在这里显示'
        }}</small>
      </div>
      <div v-for="log in filtered" :key="log.id" class="log-line">
        <time>{{ date(log.created_at) }}</time
        ><span class="log-level" :class="colorLog ? log.level.toLowerCase() : ''">{{
          log.level.toUpperCase()
        }}</span
        ><span class="log-source" :class="log.source">{{
          log.source === 'yatori' ? 'Yatori' : '管理台'
        }}</span
        ><span v-if="log.account_id" class="log-account">{{
          log.account_label || `账号 #${log.account_id}`
        }}</span
        ><span v-if="log.task_id" class="log-task">#{{ log.task_id }}</span
        ><span class="log-message">{{ log.message }}</span>
      </div>
    </div>
    <div class="log-footer">
      <span>本页保留最近 2,000 条已加载记录</span
      ><span>{{ follow ? '跟随最新记录' : '自由浏览' }}</span>
    </div>
  </section>
</template>
