<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NCollapse, NCollapseItem, NSpin, useDialog, useMessage } from 'naive-ui'
import { Bot, RefreshCw } from 'lucide-vue-next'
import { errorText, post } from '../api'
import { useResource } from '../composables/useResource'
import type { Question, QuestionSet } from '../types'
const props = defineProps<{ courseId: number }>()
const { data, error, loading, refresh } = useResource<QuestionSet[]>(
  `/courses/${props.courseId}/questions`,
  [],
)
const message = useMessage()
const dialog = useDialog()
const answers = ref<Record<string, string>>({})
const busy = ref<string | null>(null)
function plain(value: string) {
  const parsed = new DOMParser().parseFromString(value || '', 'text/html')
  return parsed.body.textContent || ''
}
function options(question: Question): string[] {
  if (Array.isArray(question.options)) return question.options.map((item) => plain(String(item)))
  if (question.options && typeof question.options === 'object')
    return Object.entries(question.options).map(([key, value]) => `${key}. ${plain(String(value))}`)
  return []
}
function preview(question: Question, key: string) {
  dialog.info({
    title: '查询答案建议',
    content: '将把题目和选项发送到已配置的题库或 AI 服务。请审核建议后在学习通完成确认。',
    positiveText: '发送并预览',
    negativeText: '取消',
    onPositiveClick: async () => {
      busy.value = key
      try {
        const result = await post<{ answer: string }>('/answers/preview', {
          question: plain(question.title),
          options: options(question),
          question_type: question.type,
        })
        answers.value[key] = result.answer
      } catch (e) {
        message.error(errorText(e))
      } finally {
        busy.value = null
      }
    },
  })
}
</script>

<template>
  <section class="question-panel">
    <div class="section-heading">
      <h3>试卷题目</h3>
      <NButton quaternary circle :loading="loading" aria-label="刷新测验题目" @click="refresh"
        ><RefreshCw :size="15"
      /></NButton>
    </div>
    <p class="form-hint">
      查看学习任务解析的章测、作业和考试题目。保存与交卷按课程配置执行，完成状态以平台确认为准。
    </p>
    <NAlert v-if="error" type="error">{{ error }}</NAlert
    ><NSpin :show="loading"
      ><NCollapse v-if="data.length"
        ><NCollapseItem
          v-for="set in data"
          :key="`${set.chapter_id}-${set.job_id}`"
          :title="`${set.chapter_id === 'work' ? '作业' : set.chapter_id === 'exam' ? '考试' : '章节 ' + set.chapter_id} · ${set.questions.length} 道题目`"
          :name="`${set.chapter_id}-${set.job_id}`"
          ><article
            v-for="(question, index) in set.questions"
            :key="question.id || index"
            class="question-card"
          >
            <h4>{{ index + 1 }}. {{ plain(question.title) }}</h4>
            <ul v-if="options(question).length">
              <li v-for="(option, optionIndex) in options(question)" :key="optionIndex">
                {{ option }}
              </li>
            </ul>
            <NButton
              size="small"
              secondary
              :loading="busy === `${set.job_id}-${index}`"
              @click="preview(question, `${set.job_id}-${index}`)"
              ><template #icon><Bot :size="15" /></template>答案建议预览</NButton
            ><NAlert
              v-if="answers[`${set.job_id}-${index}`]"
              type="info"
              class="ai-answer"
              title="答案建议 · 待你审核"
              >{{ answers[`${set.job_id}-${index}`] }}</NAlert
            >
          </article></NCollapseItem
        ></NCollapse
      >
      <p v-else-if="!loading" class="question-empty">暂无已解析题目</p></NSpin
    >
  </section>
</template>
