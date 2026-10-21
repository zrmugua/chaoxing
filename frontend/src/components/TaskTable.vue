<script setup lang="ts">
import { NButton, NTag, useDialog, useMessage } from 'naive-ui'
import { ref } from 'vue'
import { date, label, statusType } from '../format'
import { errorText, post } from '../api'
import type { Account, Course, Task } from '../types'
import EmptyState from './EmptyState.vue'
defineProps<{ tasks: Task[]; accounts?: Account[]; courses?: Course[]; compact?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const busy = ref<number | null>(null)
const message = useMessage()
const dialog = useDialog()
async function perform(task: Task, action: string) {
  busy.value = task.id
  try {
    await post(`/tasks/${task.id}/action`, { action })
    message.success('任务状态已更新')
    emit('changed')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = null
  }
}
function stop(task: Task) {
  dialog.warning({
    title: '停止任务',
    content: '将结束当前 Console 进程。再次启动时由 Console 读取平台进度。',
    positiveText: '停止任务',
    negativeText: '继续执行',
    onPositiveClick: () => perform(task, 'stop'),
  })
}
</script>

<template>
  <div v-if="tasks.length" class="table-scroll">
    <table class="data-table">
      <thead>
        <tr>
          <th>任务</th>
          <th>执行状态</th>
          <th>运行结果</th>
          <th v-if="!compact">创建时间</th>
          <th class="actions-cell">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.id">
          <td>
            <div class="cell-title">
              {{ label(task.kind) }}<span class="mono subtle">#{{ task.id }}</span>
            </div>
            <div class="cell-subtitle">
              {{
                accounts?.find((a) => a.id === task.account_id)?.label ||
                `账号 #${task.account_id}`
              }}<template v-if="task.course_id">
                ·
                {{
                  courses?.find((c) => c.id === task.course_id)?.title || `课程 #${task.course_id}`
                }}</template
              >
            </div>
            <div v-if="task.message" class="task-message">{{ task.message }}</div>
          </td>
          <td>
            <NTag :type="statusType(task.state)" size="small" round :bordered="false">{{
              label(task.state)
            }}</NTag>
            <div v-if="!compact" class="cell-subtitle">
              已启动 {{ task.attempts }} 次
            </div>
          </td>
          <td>{{ task.kind === 'study' ? '查看原始日志' : task.server_state === 'confirmed' ? '查询完成' : '等待查询结果' }}</td>
          <td v-if="!compact" class="cell-date">{{ date(task.created_at, true) }}</td>
          <td class="actions-cell">
            <div class="row-actions">
              <NButton
                v-if="['running', 'queued', 'recovering'].includes(task.state)"
                size="tiny"
                secondary
                :loading="busy === task.id"
                @click="perform(task, 'pause')"
                >暂停</NButton
              ><NButton
                v-if="task.state === 'paused'"
                size="tiny"
                secondary
                type="primary"
                :loading="busy === task.id"
                @click="perform(task, 'resume')"
                >继续</NButton
              ><NButton
                v-if="
                  [
                    'running',
                    'queued',
                    'recovering',
                    'paused',
                    'pausing',
                    'waiting_manual',
                    'awaiting_confirmation',
                  ].includes(task.state)
                "
                size="tiny"
                quaternary
                type="error"
                :disabled="busy === task.id"
                @click="stop(task)"
                >停止</NButton
              ><NButton
                v-if="
                  ['failed', 'stopped', 'waiting_manual', 'awaiting_confirmation'].includes(
                    task.state,
                  )
                "
                size="tiny"
                secondary
                :loading="busy === task.id"
                @click="perform(task, 'retry')"
                >重试</NButton
              ><RouterLink :to="`/logs?task_id=${task.id}`" class="text-link small"
                >日志</RouterLink
              >
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <EmptyState
    v-else
    title="还没有任务"
    description="在账号或课程页面创建任务，执行过程会显示在这里。"
  />
</template>
