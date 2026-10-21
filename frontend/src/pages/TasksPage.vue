<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NInput, NSelect } from 'naive-ui'
import { Plus, RefreshCw, Search } from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import TaskTable from '../components/TaskTable.vue'
import { useResource } from '../composables/useResource'
import type { Account, Course, Task } from '../types'

const tasks = useResource<Task[]>('/tasks', [], 3000)
const accounts = useResource<Account[]>('/accounts', [])
const courses = useResource<Course[]>('/courses', [])
const state = ref('all')
const accountId = ref<number | null>(null)
const search = ref('')
const tabs = [
  { key: 'all', text: '全部任务' },
  { key: 'active', text: '执行中' },
  { key: 'paused', text: '已暂停' },
  { key: 'attention', text: '需关注' },
  { key: 'finished', text: '已结束' },
]
function matches(task: Task, key: string) {
  if (key === 'active')
    return [
      'running',
      'pending',
      'queued',
      'retrying',
      'pausing',
      'stopping',
      'recovering',
    ].includes(task.state)
  if (key === 'paused') return task.state === 'paused'
  if (key === 'attention')
    return [
      'failed',
      'interrupted',
      'awaiting_user',
      'blocked',
      'needs_attention',
      'waiting_manual',
      'awaiting_confirmation',
    ].includes(task.state)
  if (key === 'finished')
    return ['completed', 'succeeded', 'cancelled', 'stopped'].includes(task.state)
  return true
}
const filtered = computed(() =>
  tasks.data.value.filter(
    (task) =>
      matches(task, state.value) &&
      (!accountId.value || task.account_id === accountId.value) &&
      `${task.id} ${task.message} ${courses.data.value.find((c) => c.id === task.course_id)?.title || ''}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
)
const options = computed(() => accounts.data.value.map((a) => ({ label: a.label, value: a.id })))
</script>

<template>
  <PageHeading title="任务队列" description="查看 Console 进程状态，暂停、停止或重新启动任务。"
    ><NButton :loading="tasks.loading.value" @click="tasks.refresh"
      ><template #icon><RefreshCw :size="15" /></template>刷新</NButton
    ><RouterLink to="/courses"
      ><NButton type="primary"
        ><template #icon><Plus :size="16" /></template>创建学习任务</NButton
      ></RouterLink
    ></PageHeading
  ><NAlert v-if="tasks.error.value" type="error" class="mb-20">{{ tasks.error.value }}</NAlert>
  <div class="info-strip">
    <span class="status-dot online" /><span
      >任务状态每 3 秒更新。执行结束表示 Console 已退出，课程进度请在课程页同步查看。</span
    >
  </div>
  <section class="panel">
    <div class="task-tabs" role="tablist" aria-label="按任务状态筛选">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        role="tab"
        :aria-selected="state === tab.key"
        :class="{ active: state === tab.key }"
        @click="state = tab.key"
      >
        {{ tab.text }}<span>{{ tasks.data.value.filter((t) => matches(t, tab.key)).length }}</span>
      </button>
    </div>
    <div class="table-filter">
      <NInput
        v-model:value="search"
        placeholder="搜索任务编号、课程或运行提示"
        clearable
        class="search-input"
        ><template #prefix><Search :size="15" /></template></NInput
      ><NSelect
        v-model:value="accountId"
        :options="options"
        placeholder="全部账号"
        clearable
        class="account-select"
      />
    </div>
    <TaskTable
      :tasks="filtered"
      :accounts="accounts.data.value"
      :courses="courses.data.value"
      @changed="tasks.refresh"
    />
  </section>
  <p class="page-note">暂停与停止将在任务的安全检查点生效。人工处理完成后，可从任务操作中重试。</p>
</template>
