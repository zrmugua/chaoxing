<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NTag, useMessage } from 'naive-ui'
import { useResource } from '../composables/useResource'
import { errorText, post } from '../api'
const props = defineProps<{ courseId: number }>()
interface Assessment {
  id: number
  kind: string
  title: string
  status: string
  remaining: string
}
const { data, error, refresh } = useResource<Assessment[]>(
  `/courses/${props.courseId}/assessments`,
  [],
)
const busy = ref(false)
const message = useMessage()
async function sync() {
  busy.value = true
  try {
    await post(`/courses/${props.courseId}/assessments/sync`)
    message.success('列表同步任务已加入队列')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <section class="question-panel">
    <div class="section-heading">
      <h3>作业与考试</h3>
      <div>
        <NButton size="small" quaternary @click="refresh">刷新</NButton
        ><NButton size="small" :loading="busy" @click="sync">同步列表</NButton>
      </div>
    </div>
    <p class="form-hint">
      查看学习通返回的作业、考试状态与剩余时间。答题按账号课程配置执行，可在此同步最新结果。
    </p>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <article v-for="item in data" :key="item.id" class="question-card">
      <NTag size="small" :bordered="false">{{ item.kind === 'work' ? '作业' : '考试' }}</NTag>
      <h4>{{ item.title }}</h4>
      <p class="muted">{{ item.status || '状态待确认' }} {{ item.remaining }}</p>
    </article>
    <p v-if="!data.length" class="question-empty">暂无已同步的作业与考试</p>
  </section>
</template>
