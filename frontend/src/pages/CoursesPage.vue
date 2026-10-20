<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NAlert,
  NButton,
  NDrawer,
  NDrawerContent,
  NInput,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  ArrowRight,
  BookOpen,
  CheckCheck,
  Layers3,
  LockKeyhole,
  RefreshCw,
  Search,
} from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import EmptyState from '../components/EmptyState.vue'
import QuestionPanel from '../components/QuestionPanel.vue'
import AssessmentsPanel from '../components/AssessmentsPanel.vue'
import RunConfirmation from '../components/RunConfirmation.vue'
import { useResource } from '../composables/useResource'
import { api, errorText, post } from '../api'
import { date } from '../format'
import type { Account, Chapter, Course } from '../types'

const courses = useResource<Course[]>('/courses', [], 8000)
const accounts = useResource<Account[]>('/accounts', [])
const accountId = ref<number | null>(null)
const search = ref('')
const message = useMessage()
const showRun = ref(false)
const runAccount = ref<number | null>(null)
const runCourse = ref<number | undefined>()
const selected = ref<Course | null>(null)
const showDrawer = ref(false)
const chapters = ref<Chapter[]>([])
const chapterLoading = ref(false)
const chapterError = ref('')
const busy = ref<number | null>(null)
const options = computed(() => accounts.data.value.map((a) => ({ label: a.label, value: a.id })))
const filtered = computed(() =>
  courses.data.value.filter(
    (c) =>
      (!accountId.value || c.account_id === accountId.value) &&
      `${c.title} ${c.teacher}`.toLowerCase().includes(search.value.toLowerCase()),
  ),
)
async function openChapters(course: Course) {
  selected.value = course
  showDrawer.value = true
  chapters.value = []
  chapterError.value = ''
  chapterLoading.value = true
  try {
    chapters.value = await api<Chapter[]>(`/courses/${course.id}/chapters`)
  } catch (e) {
    chapterError.value = errorText(e)
  } finally {
    chapterLoading.value = false
  }
}
async function execute(course: Course, action: string) {
  busy.value = course.id
  try {
    await post(`/courses/${course.id}/${action}`)
    message.success(action === 'sync' ? '章节同步任务已加入队列' : '学习任务已加入队列')
    await courses.refresh()
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = null
  }
}
function batchStudy() {
  if (!accountId.value) {
    message.info('请先选择一个账号')
    return
  }
  runAccount.value = accountId.value
  runCourse.value = undefined
  showRun.value = true
}
function study(course: Course) {
  runAccount.value = course.account_id
  runCourse.value = course.id
  showRun.value = true
}
</script>

<template>
  <RunConfirmation v-model:show="showRun" :account-id="runAccount" :course-id="runCourse" />
  <PageHeading title="课程列表" description="按账号查看课程，管理章节与学习任务。"
    ><NButton :loading="courses.loading.value" @click="courses.refresh"
      ><template #icon><RefreshCw :size="15" /></template>刷新课程</NButton
    ><RouterLink to="/accounts"
      ><NButton type="primary"
        >同步账号课程<template #icon><ArrowRight :size="16" /></template></NButton></RouterLink
  ></PageHeading>
  <NAlert v-if="courses.error.value || accounts.error.value" type="error" class="mb-20">{{
    courses.error.value || accounts.error.value
  }}</NAlert>
  <div class="filter-bar">
    <div class="filter-inputs">
      <NInput v-model:value="search" placeholder="搜索课程或教师" clearable class="search-input"
        ><template #prefix><Search :size="16" /></template></NInput
      ><NSelect
        v-model:value="accountId"
        :options="options"
        placeholder="全部账号"
        clearable
        class="account-select"
      />
    </div>
    <NButton type="primary" secondary :disabled="!accountId" @click="batchStudy"
      >按账号规则创建任务</NButton
    >
    <span class="muted">{{ filtered.length }} 门课程</span>
  </div>
  <div v-if="filtered.length" class="course-grid">
    <article v-for="course in filtered" :key="course.id" class="course-card">
      <div class="course-card-top">
        <span class="course-icon"><BookOpen :size="25" :stroke-width="1.5" /></span
        ><NTag size="small" :bordered="false" class="course-account">{{
          accounts.data.value.find((a) => a.id === course.account_id)?.label ||
          `账号 #${course.account_id}`
        }}</NTag>
      </div>
      <h2>{{ course.title }}</h2>
      <p class="course-teacher">{{ course.teacher || '教师信息待同步' }}</p>
      <div class="course-meta">
        <span><Layers3 :size="14" />课程 {{ course.remote_id }}</span
        ><span>同步于 {{ date(course.synced_at, true) }}</span>
      </div>
      <div class="course-actions">
        <NButton size="small" secondary @click="openChapters(course)">查看章节</NButton
        ><NButton
          size="small"
          quaternary
          :loading="busy === course.id"
          @click="execute(course, 'sync')"
          >同步</NButton
        ><NButton size="small" type="primary" :disabled="busy === course.id" @click="study(course)"
          >创建学习任务</NButton
        >
      </div>
    </article>
  </div>
  <section v-else class="panel">
    <EmptyState
      :title="search || accountId ? '没有找到匹配的课程' : '暂无已同步课程'"
      :description="
        search || accountId
          ? '调整搜索内容或账号筛选后再试。'
          : '在账号管理中完成登录并同步课程，课程内容就会出现在这里。'
      "
      ><RouterLink v-if="!search && !accountId" to="/accounts"
        ><NButton type="primary">前往账号管理</NButton></RouterLink
      ></EmptyState
    >
  </section>
  <NDrawer v-model:show="showDrawer" :width="'min(560px, 100vw)'"
    ><NDrawerContent :title="selected?.title || '课程章节'" closable
      ><div class="drawer-summary">
        <span class="course-icon"><BookOpen :size="26" /></span>
        <div>
          <strong>课程章节</strong>
          <p>{{ selected?.teacher || '学习通课程' }} · {{ chapters.length }} 个章节</p>
        </div>
        <NButton
          size="small"
          aria-label="刷新章节"
          :loading="chapterLoading"
          @click="selected && openChapters(selected)"
          ><RefreshCw :size="14"
        /></NButton>
      </div>
      <NAlert type="info" class="mb-20"
        >章节确认状态来自最近一次平台查询。同步章节后刷新本面板可查看最新结果。</NAlert
      ><NAlert v-if="chapterError" type="error">{{ chapterError }}</NAlert
      ><NSpin :show="chapterLoading"
        ><div v-if="chapters.length" class="chapter-list">
          <div v-for="(chapter, index) in chapters" :key="chapter.id" class="chapter-item">
            <span class="chapter-number">{{ String(index + 1).padStart(2, '0') }}</span>
            <div>
              <h3>{{ chapter.title }}</h3>
              <p>{{ chapter.job_count }} 个任务点 · {{ date(chapter.synced_at, true) }}</p>
            </div>
            <NTag
              :type="chapter.confirmed ? 'success' : chapter.locked ? 'warning' : 'default'"
              size="small"
              :bordered="false"
              ><template #icon
                ><CheckCheck v-if="chapter.confirmed" :size="13" /><LockKeyhole
                  v-else-if="chapter.locked"
                  :size="13" /></template
              >{{ chapter.confirmed ? '平台已确认' : chapter.locked ? '待解锁' : '待完成' }}</NTag
            >
          </div>
        </div>
        <EmptyState
          v-else-if="!chapterLoading"
          title="章节尚未同步"
          description="创建章节同步任务，完成后刷新查看。"
          ><NButton :loading="busy === selected?.id" @click="selected && execute(selected, 'sync')"
            >同步章节</NButton
          ></EmptyState
        ></NSpin
      ><QuestionPanel
        v-if="selected"
        :key="selected.id"
        :course-id="selected.id"
      /><AssessmentsPanel
        v-if="selected"
        :key="`assessments-${selected.id}`"
        :course-id="selected.id"
      /><template #footer
        ><NButton
          type="primary"
          :loading="busy === selected?.id"
          @click="selected && study(selected)"
          >创建学习任务</NButton
        ></template
      ></NDrawerContent
    ></NDrawer
  >
</template>
