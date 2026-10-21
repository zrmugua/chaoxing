<script setup lang="ts">
import { computed } from 'vue'
import { NAlert, NButton, NTag } from 'naive-ui'
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  ClipboardList,
  RefreshCw,
  Server,
  UsersRound,
} from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import TaskTable from '../components/TaskTable.vue'
import { useResource } from '../composables/useResource'
import { date } from '../format'
import type { Account, Course, Dashboard, Task } from '../types'

const summary = useResource<Dashboard>(
  '/dashboard',
  { accounts: 0, courses: 0, tasks: 0, states: {}, worker_online: false, heartbeat: null },
  5000,
)
const tasks = useResource<Task[]>('/tasks', [], 5000)
const accounts = useResource<Account[]>('/accounts', [])
const courses = useResource<Course[]>('/courses', [])
const running = computed(() => summary.data.value.states.running || 0)
const complete = computed(
  () => (summary.data.value.states.completed || 0) + (summary.data.value.states.succeeded || 0),
)
const recent = computed(() => tasks.data.value.slice(0, 5))
const stateGroups = [
  { label: '执行中', tone: 'running', states: ['running'] },
  { label: '等待执行', tone: 'queued', states: ['pending', 'queued', 'retrying', 'recovering'] },
  { label: '执行结束', tone: 'completed', states: ['completed', 'succeeded'] },
  {
    label: '待人工处理',
    tone: 'manual',
    states: [
      'waiting',
      'awaiting_user',
      'needs_attention',
      'blocked',
      'waiting_manual',
      'awaiting_confirmation',
    ],
  },
  { label: '失败 / 中断', tone: 'failed', states: ['failed', 'interrupted'] },
  {
    label: '暂停 / 停止',
    tone: 'paused',
    states: ['paused', 'pausing', 'stopping', 'stopped', 'cancelled'],
  },
]
const stateRows = computed(() => {
  const states = summary.data.value.states
  const rows = stateGroups.map((group) => ({
    ...group,
    count: group.states.reduce((total, state) => total + (states[state] || 0), 0),
  }))
  const knownStates = new Set(stateGroups.flatMap((group) => group.states))
  const other = Object.entries(states).reduce(
    (total, [state, count]) => total + (knownStates.has(state) ? 0 : count),
    0,
  )
  if (other) rows.push({ label: '其他状态', tone: 'other', states: [], count: other })
  return rows
})
const queued = computed(() => stateRows.value.find((row) => row.tone === 'queued')?.count || 0)
const failed = computed(() => stateRows.value.find((row) => row.tone === 'failed')?.count || 0)

function refresh() {
  void summary.refresh()
  void tasks.refresh()
  void accounts.refresh()
  void courses.refresh()
}
</script>

<template>
  <PageHeading
    title="任务概况"
    description="查看任务执行情况与后台运行状态。"
    eyebrow="TASK OVERVIEW"
  >
    <NButton :loading="summary.loading.value" @click="refresh">
      <template #icon><RefreshCw :size="15" /></template>刷新概况
    </NButton>
  </PageHeading>
  <NAlert v-if="summary.error.value || tasks.error.value" type="error" class="mb-20">
    {{ summary.error.value || tasks.error.value }}
  </NAlert>

  <section class="stat-grid" aria-label="任务与资源统计">
    <article class="stat-card stat-card-primary">
      <div class="stat-label">任务总数<ClipboardList :size="18" /></div>
      <div class="stat-value">{{ summary.data.value.tasks }}<span>项</span></div>
      <span class="stat-note">{{ complete }} 项执行结束 · {{ failed }} 项失败或中断</span>
    </article>
    <article class="stat-card">
      <div class="stat-label">正在执行<Activity :size="18" /></div>
      <div class="stat-value">{{ running }}<span>项</span></div>
      <span class="stat-note">{{ queued }} 项等待执行</span>
    </article>
    <article class="stat-card">
      <div class="stat-label">学习通账号<UsersRound :size="18" /></div>
      <div class="stat-value">{{ summary.data.value.accounts }}<span>个</span></div>
      <RouterLink to="/accounts" class="stat-link">管理账号<ArrowUpRight :size="13" /></RouterLink>
    </article>
    <article class="stat-card">
      <div class="stat-label">已同步课程<BookOpen :size="18" /></div>
      <div class="stat-value">{{ summary.data.value.courses }}<span>门</span></div>
      <RouterLink to="/courses" class="stat-link">浏览课程<ArrowUpRight :size="13" /></RouterLink>
    </article>
  </section>

  <div class="worker-notice" :class="{ online: summary.data.value.worker_online }" role="status">
    <Server :size="17" />
    <div class="worker-notice-copy">
      <strong>{{ summary.data.value.worker_online ? 'Worker 在线' : 'Worker 离线' }}</strong>
      <span>{{
        summary.data.value.worker_online
          ? 'Console 管理服务在线，任务在设备后台运行。'
          : '最近未收到心跳，请确认后台执行器已启动。'
      }}</span>
    </div>
    <span class="worker-heartbeat">每 5 秒更新</span>
  </div>

  <div class="dashboard-grid">
    <section class="panel dashboard-recent">
      <div class="panel-heading">
        <div>
          <h2>
            最近任务<span class="count-badge">{{ summary.data.value.tasks }}</span>
          </h2>
          <p>最近 5 项任务 · 执行结果见原始日志</p>
        </div>
        <RouterLink to="/tasks" class="text-link">全部任务<ArrowUpRight :size="15" /></RouterLink>
      </div>
      <TaskTable
        :tasks="recent"
        :accounts="accounts.data.value"
        :courses="courses.data.value"
        compact
        @changed="refresh"
      />
    </section>

    <aside class="dashboard-side">
      <section class="panel task-state-panel">
        <div class="panel-heading">
          <div>
            <h2>任务状态分布</h2>
            <p>按当前执行状态汇总</p>
          </div>
          <ClipboardList :size="17" class="muted" />
        </div>
        <div class="task-state-list">
          <div
            v-for="row in stateRows"
            :key="row.tone"
            class="task-state-row"
            :class="`tone-${row.tone}`"
          >
            <div class="task-state-label">
              <span>{{ row.label }}</span
              ><strong>{{ row.count }}</strong>
            </div>
            <div class="task-state-track" aria-hidden="true">
              <span
                class="task-state-fill"
                :style="{
                  width: `${summary.data.value.tasks ? Math.min(100, (row.count / summary.data.value.tasks) * 100) : 0}%`,
                }"
              />
            </div>
          </div>
        </div>
      </section>
      <section class="panel runtime-card">
        <div class="panel-heading">
          <h2>运行情况</h2>
          <Activity :size="17" class="muted" />
        </div>
        <div class="runtime-row">
          <span>后台执行器</span>
          <NTag
            :type="summary.data.value.worker_online ? 'success' : 'warning'"
            size="small"
            :bordered="false"
          >
            {{ summary.data.value.worker_online ? '在线' : '离线' }}
          </NTag>
        </div>
        <div class="runtime-row">
          <span>最近心跳</span
          ><span class="cell-date">{{ date(summary.data.value.heartbeat, true) }}</span>
        </div>
        <p class="runtime-note">平台提示和执行详情请查看账号的 Console 日志。</p>
      </section>
    </aside>
  </div>

  <section class="panel dashboard-shortcuts" aria-label="快捷操作">
    <RouterLink to="/accounts" class="shortcut-item">
      <span class="shortcut-icon"><UsersRound :size="19" /></span>
      <div class="shortcut-copy">
        <h3>账号管理</h3>
        <p>添加账号与登录验证</p>
      </div>
      <ArrowRight :size="16" />
    </RouterLink>
    <RouterLink to="/courses" class="shortcut-item">
      <span class="shortcut-icon"><BookOpen :size="19" /></span>
      <div class="shortcut-copy">
        <h3>课程管理</h3>
        <p>同步课程与安排学习</p>
      </div>
      <ArrowRight :size="16" />
    </RouterLink>
    <RouterLink to="/tasks" class="shortcut-item">
      <span class="shortcut-icon"><ClipboardList :size="19" /></span>
      <div class="shortcut-copy">
        <h3>任务管理</h3>
        <p>查看进度与处理任务</p>
      </div>
      <ArrowRight :size="16" />
    </RouterLink>
  </section>
</template>
