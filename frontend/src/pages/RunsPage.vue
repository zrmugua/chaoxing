<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NInputNumber, NTag } from 'naive-ui'
import { RefreshCw } from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import EmptyState from '../components/EmptyState.vue'
import { useResource } from '../composables/useResource'
import { date, duration, label, statusType } from '../format'
import type { Run } from '../types'

const { data, error, loading, refresh } = useResource<Run[]>('/runs', [], 5000)
const taskId = ref<number | null>(null)
const filtered = computed(() =>
  data.value.filter((run) => !taskId.value || run.task_id === taskId.value),
)
</script>

<template>
  <PageHeading title="运行记录" description="保存每次执行的起止时间、尝试次数和结果。"
    ><NButton :loading="loading" @click="refresh"
      ><template #icon><RefreshCw :size="15" /></template>刷新记录</NButton
    ></PageHeading
  ><NAlert v-if="error" type="error" class="mb-20">{{ error }}</NAlert>
  <section class="panel">
    <div class="panel-heading">
      <h2>
        执行历史<span class="count-badge">{{ filtered.length }}</span>
      </h2>
      <NInputNumber
        v-model:value="taskId"
        :min="1"
        :show-button="false"
        clearable
        placeholder="按任务 ID 筛选"
        style="width: 170px"
      />
    </div>
    <div v-if="filtered.length" class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>执行记录</th>
            <th>状态</th>
            <th>开始时间</th>
            <th>结束时间</th>
            <th>耗时</th>
            <th>结果说明</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in filtered" :key="run.id">
            <td>
              <div class="cell-title">任务 #{{ run.task_id }}</div>
              <div class="cell-subtitle">第 {{ run.attempt }} 次尝试 · 记录 #{{ run.id }}</div>
            </td>
            <td>
              <NTag :type="statusType(run.state)" size="small" :bordered="false" round>{{
                label(run.state)
              }}</NTag>
            </td>
            <td class="cell-date">{{ date(run.started_at, true) }}</td>
            <td class="cell-date">{{ date(run.finished_at, true) }}</td>
            <td class="cell-date">{{ duration(run.started_at, run.finished_at) }}</td>
            <td class="run-message">{{ run.message || '—' }}</td>
            <td>
              <RouterLink :to="`/logs?task_id=${run.task_id}`" class="text-link small"
                >查看日志</RouterLink
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState
      v-else
      title="执行记录会保存在这里"
      description="后台任务启动后，可在这里查看每一次尝试的详情。"
    />
  </section>
</template>
