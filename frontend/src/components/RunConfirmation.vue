<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NDescriptions,
  NDescriptionsItem,
  NModal,
  NSpace,
  NSpin,
  useMessage,
} from 'naive-ui'
import { api, errorText, post } from '../api'
import type { StudySettings } from '../types'
const props = defineProps<{ show: boolean; accountId: number | null; courseId?: number }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; started: [] }>()
const message = useMessage(),
  loading = ref(false),
  starting = ref(false),
  error = ref('')
const plan = ref<{
  rules: StudySettings
  courses: { id: number; title: string }[]
  count: number
  fingerprint: string
  will_submit: boolean
} | null>(null)
const videoLabels = {
  off: '关闭',
  normal: '普通模式',
  multi_course: '多课程同时进行',
  multi_node: '多任务点同时进行',
}
const answerLabels = {
  off: '关闭自动答题',
  ai: 'AI 大模型',
  question_bank: '外置题库',
  chaoxing_ai: '学习通内置 AI',
}
const submitLabels = { save: '不交卷，只保存', submit: '答题后直接交卷', complete: '无空题时交卷' }
async function load() {
  plan.value = null
  error.value = ''
  loading.value = true
  try {
    plan.value = await api(
      `/accounts/${props.accountId}/study-plan${props.courseId ? '?course_id=' + props.courseId : ''}`,
    )
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
async function start() {
  if (!plan.value) return
  starting.value = true
  try {
    const result = await post<any>(
      props.courseId ? `/courses/${props.courseId}/study` : `/accounts/${props.accountId}/study`,
      { fingerprint: plan.value.fingerprint },
    )
    message.success(
      props.courseId
        ? '学习任务已加入队列'
        : `已创建 ${result.tasks.length} 个任务，${result.skipped} 个已在队列中`,
    )
    emit('update:show', false)
    emit('started')
  } catch (e) {
    error.value = errorText(e)
    plan.value = null
  } finally {
    starting.value = false
  }
}
watch(
  () => [props.show, props.accountId, props.courseId],
  () => {
    if (props.show && props.accountId) void load()
  },
)
</script>
<template>
  <NModal
    :show="show"
    preset="card"
    title="确认开始运行"
    class="form-modal"
    :mask-closable="!starting"
    @update:show="emit('update:show', $event)"
  >
    <NSpin :show="loading"
      ><NAlert v-if="error" type="error" class="mb-20"
        >{{ error }} <NButton text @click="load">重新读取</NButton></NAlert
      >
      <template v-if="plan"
        ><NDescriptions :column="1" label-placement="left" bordered>
          <NDescriptionsItem label="课程范围">{{ plan.count }} 门课程</NDescriptionsItem>
          <NDescriptionsItem label="视频模式">{{
            videoLabels[plan.rules.video_mode]
          }}</NDescriptionsItem>
          <NDescriptionsItem label="答题模式">{{
            answerLabels[plan.rules.answer_mode]
          }}</NDescriptionsItem>
          <NDescriptionsItem v-if="plan.rules.answer_mode !== 'off'" label="答题提交">{{
            submitLabels[plan.rules.submit_mode]
          }}</NDescriptionsItem>
          <NDescriptionsItem v-if="plan.rules.answer_mode !== 'off'" label="试卷类型"
            >章测 {{ plan.rules.chapter_test ? '开' : '关' }} · 作业
            {{ plan.rules.work ? '开' : '关' }} · 考试
            {{ plan.rules.exam ? '开' : '关' }}</NDescriptionsItem
          >
          <NDescriptionsItem v-if="plan.rules.video_mode === 'multi_node'" label="同时任务点">{{
            plan.rules.node_concurrency
          }}</NDescriptionsItem>
        </NDescriptions>
        <div class="run-course-list">
          <div v-for="course in plan.courses" :key="course.id">{{ course.title }}</div>
        </div>
        <NAlert :type="plan.will_submit ? 'warning' : 'info'" class="mb-20"
          >{{
            plan.will_submit
              ? '本次运行允许自动交卷，请确认课程与配置。'
              : '任务在后台执行，关闭浏览器后仍会继续。'
          }}
          完成状态将由学习通服务端回读确认。</NAlert
        ></template
      >
      <NSpace justify="end"
        ><NButton :disabled="starting" @click="emit('update:show', false)">取消</NButton
        ><NButton
          type="primary"
          :loading="starting"
          :disabled="!plan?.count || loading"
          @click="start"
          >开始运行</NButton
        ></NSpace
      >
    </NSpin>
  </NModal>
</template>
<style scoped>
.run-course-list {
  max-height: 160px;
  overflow: auto;
  line-height: 1.8;
  margin: 16px 0;
  padding: 12px;
  border-radius: 8px;
}
</style>
