<script setup lang="ts">
import { NButton, NProgress, NTag, useDialog, useMessage } from 'naive-ui'
import { ref } from 'vue'
import { date, label, progress, serverLabel, statusType } from '../format'
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
    content: '当前任务会在安全检查点停止。已由平台确认的进度将保留。',
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
          <th>平台确认</th>
          <th>执行进度</th>
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
              第 {{ task.attempts }} / {{ task.max_attempts }} 次尝试
            </div>
          </td>
          <td>
            <NTag :type="statusType(task.server_state)" size="small" :bordered="false">{{
              serverLabel(task.server_state, task.kind)
            }}</NTag>
          </td>
          <td class="progress-cell">
            <NProgress
              type="line"
              :percentage="Math.round(progress(task.progress))"
              :height="5"
              :show-indicator="true"
              :status="task.state === 'failed' ? 'error' : 'default'"
            />
          </td>
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
