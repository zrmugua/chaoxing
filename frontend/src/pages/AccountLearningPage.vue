<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  NAlert,
  NButton,
  NDrawer,
  NDrawerContent,
  NInput,
  NModal,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  ArrowLeft,
  BookOpen,
  CheckCheck,
  Clock3,
  Pause,
  Play,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Square,
} from 'lucide-vue-next'
import { api, errorText } from '../api'
import { date, progress, statusType } from '../format'
import type { Chapter, LearningAction, LearningCourse, StudySettings } from '../types'
import PageHeading from '../components/PageHeading.vue'
import EmptyState from '../components/EmptyState.vue'
import LearningRulesPanel from '../components/LearningRulesPanel.vue'
import AccountLogs from '../components/AccountLogs.vue'
import { useAccountLearning } from '../composables/useAccountLearning'

const route = useRoute()
const accountId = computed(() => Number(route.params.id))
const {
  data,
  selection,
  dirty,
  loading,
  busy,
  error,
  conflict,
  settingsPending,
  updatedAt,
  refresh,
  perform,
  restore,
} = useAccountLearning(accountId)
const message = useMessage()
const search = ref('')
const showRules = ref(false)
const preparing = ref(false)
const rules = ref<StudySettings | null>(null)
const overridden = ref(false)
type RunIntent = 'save' | 'start' | 'resume'
const review = ref<{
  kind: RunIntent
  fingerprint: string
  rules: StudySettings
  courses: string[]
  courseIds: number[]
  revision: number
} | null>(null)
const chapterCourse = ref<LearningCourse | null>(null)
const chapters = ref<Chapter[]>([])
const chapterLoading = ref(false)
const chapterError = ref('')
let chapterRequest = 0

const stateLabels: Record<string, string> = {
  idle: '待开始',
  queued: '等待执行',
  running: '学习中',
  applying: '正在应用选择',
  pausing: '正在暂停',
  paused: '已暂停',
  stopping: '正在停止',
  stopped: '已停止',
  refreshing: '正在同步课程与进度',
  completed: '执行结束',
  failed: '运行异常',
}
const videoLabels: Record<string, string> = {
  off: '视频关闭',
  normal: '按课程学习',
  multi_course: '多课程同时学习',
  multi_node: '多任务点同时学习',
}
const answerLabels: Record<string, string> = {
  off: '自动答题关闭',
  ai: 'AI 自动答题',
  question_bank: '题库自动答题',
  chaoxing_ai: '学习通 AI 答题',
}
const blocked = computed(() => !!busy.value || preparing.value)
const runningIntent = computed(() => data.value?.desired_state === 'running')
const canPause = computed(
  () => runningIntent.value && !['pausing', 'stopping'].includes(data.value?.state || ''),
)
const canStop = computed(
  () =>
    data.value &&
    (data.value.desired_state !== 'stopped' ||
      ['running', 'queued', 'applying', 'refreshing'].includes(data.value.state)),
)
const visibleCourses = computed(() =>
  (data.value?.courses || []).filter((course) =>
    `${course.title} ${course.teacher}`.toLowerCase().includes(search.value.toLowerCase()),
  ),
)
const selectableCourses = computed(() =>
  visibleCourses.value.filter((course) => course.available !== false),
)
const selectedCount = computed(() => selection.value.length)
const allVisibleSelected = computed(
  () =>
    selectableCourses.value.length > 0 &&
    selectableCourses.value.every((course) => selection.value.includes(course.id)),
)
const someVisibleSelected = computed(
  () =>
    selectableCourses.value.some((course) => selection.value.includes(course.id)) &&
    !allVisibleSelected.value,
)
const chosenTitles = computed(() =>
  (data.value?.courses || [])
    .filter((course) => selection.value.includes(course.id))
    .map((course) => course.title),
)
const missingSelection = computed(() =>
  selection.value.filter((id) => !data.value?.courses.some((course) => course.id === id)),
)
const unavailableSelection = computed(() =>
  (data.value?.courses || []).some(
    (course) => course.available === false && selection.value.includes(course.id),
  ),
)
const activeTitles = computed(() => data.value?.active_course_titles || [])
const paperTypes = (config: StudySettings) =>
  [config.chapter_test && '章节测验', config.work && '课程作业', config.exam && '课程考试']
    .filter(Boolean)
    .join('、')

function toggleCourse(id: number, checked: boolean) {
  selection.value = checked
    ? [...new Set([...selection.value, id])]
    : selection.value.filter((value) => value !== id)
}
function toggleVisible(checked: boolean) {
  const ids = selectableCourses.value.map((course) => course.id)
  selection.value = checked
    ? [...new Set([...selection.value, ...ids])]
    : selection.value.filter((id) => !ids.includes(id))
}
async function loadRules() {
  const id = accountId.value
  try {
    const next = await api<{ rules: StudySettings; overridden: boolean }>(
      `/accounts/${id}/study-settings`,
    )
    if (id !== accountId.value) return
    rules.value = next.rules
    overridden.value = next.overridden
  } catch {
    /* The next start or apply reads the rules again and reports any error. */
  }
}
async function rulesSaved() {
  settingsPending.value = true
  showRules.value = false
  await loadRules()
}
async function executeIntent(kind: RunIntent, fingerprint?: string) {
  const id = accountId.value
  review.value = null
  if (kind === 'save') {
    if (await perform('save', fingerprint))
      message.success(runningIntent.value ? '课程与规则已保存，正在应用' : '学习选择已保存')
    return
  }
  if (dirty.value || settingsPending.value) {
    if (!(await perform('save', fingerprint)) || accountId.value !== id) return
  }
  if (await perform(kind, fingerprint))
    message.success(kind === 'resume' ? '已恢复学习' : '已开始学习')
}
async function confirmReview() {
  const confirmed = review.value
  if (!confirmed || !data.value) return
  const unchanged =
    confirmed.revision === data.value.revision &&
    confirmed.courseIds.length === selection.value.length &&
    confirmed.courseIds.every((id) => selection.value.includes(id))
  if (!unchanged) {
    review.value = null
    message.warning('课程选择已更新，请重新核对自动交卷范围。')
    return
  }
  await executeIntent(confirmed.kind, confirmed.fingerprint)
}
async function prepare(kind: RunIntent) {
  if (blocked.value) return
  if (kind === 'save' && (!runningIntent.value || !selectedCount.value)) {
    await executeIntent(kind)
    return
  }
  const id = accountId.value
  preparing.value = true
  try {
    const plan = await api<{ rules: StudySettings; fingerprint: string }>(
      `/accounts/${id}/study-plan`,
    )
    if (id !== accountId.value) return
    rules.value = plan.rules
    const willRun = kind !== 'save' || runningIntent.value
    const willSubmit =
      willRun &&
      selectedCount.value > 0 &&
      plan.rules.answer_mode !== 'off' &&
      plan.rules.submit_mode !== 'save' &&
      !!paperTypes(plan.rules)
    if (willSubmit)
      review.value = {
        kind,
        fingerprint: plan.fingerprint,
        rules: plan.rules,
        courses: [...chosenTitles.value],
        courseIds: [...selection.value],
        revision: data.value!.revision,
      }
    else await executeIntent(kind, plan.fingerprint)
  } catch (e) {
    if (id === accountId.value) message.error(errorText(e))
  } finally {
    if (id === accountId.value) preparing.value = false
  }
}
async function action(kind: LearningAction) {
  if (await perform(kind)) {
    if (kind === 'refresh') message.success('正在同步课程和平台章节进度')
    else message.success(kind === 'pause' ? '已请求暂停学习' : '已请求停止学习')
  }
}
async function openChapters(course: LearningCourse) {
  chapterCourse.value = course
  chapters.value = []
  chapterError.value = ''
  chapterLoading.value = true
  const current = ++chapterRequest
  const id = accountId.value
  try {
    const next = await api<Chapter[]>(`/courses/${course.id}/chapters`)
    if (id === accountId.value && current === chapterRequest) chapters.value = next
  } catch (e) {
    if (id === accountId.value && current === chapterRequest) chapterError.value = errorText(e)
  } finally {
    if (id === accountId.value && current === chapterRequest) chapterLoading.value = false
  }
}
watch(
  accountId,
  () => {
    search.value = ''
    showRules.value = false
    review.value = null
    rules.value = null
    preparing.value = false
    chapterCourse.value = null
    chapters.value = []
    chapterRequest++
    void loadRules()
  },
  { immediate: true },
)
</script>

<template>
  <div class="account-learning">
    <RouterLink to="/accounts" class="text-link account-back"
      ><ArrowLeft :size="15" />学习账号</RouterLink
    >
    <PageHeading
      :title="data?.account.label || '账号学习'"
      description="选择课程并开始学习，运行过程中可随时调整。"
    >
      <RouterLink :to="{ path: '/runs', query: { account_id: accountId } }"
        ><NButton
          ><template #icon><Clock3 :size="15" /></template>运行记录</NButton
        ></RouterLink
      >
      <NButton :disabled="!data || blocked" @click="showRules = true"
        ><template #icon><Settings2 :size="15" /></template>学习规则</NButton
      >
    </PageHeading>
    <NAlert v-if="error" type="error" class="mb-20"
      >{{ error }}<NButton text :disabled="blocked" @click="refresh">重新读取</NButton></NAlert
    >
    <NAlert v-if="conflict" type="warning" class="mb-20">
      本页勾选已保留。请核对服务器提示与最新状态，调整后再次保存或开始。
      <NButton text :disabled="blocked" @click="restore">使用服务器已保存的选择</NButton>
    </NAlert>
    <NSpin v-if="loading && !data" class="account-initial-loading" />
    <template v-if="data">
      <section class="panel learning-status" aria-labelledby="learning-status-title">
        <div class="learning-status-top">
          <div class="learning-status-title">
            <h2 id="learning-status-title">学习状态</h2>
            <NTag :type="statusType(data.state)" :bordered="false" round>{{
              stateLabels[data.state] || data.state
            }}</NTag>
          </div>
          <span class="muted status-updated">状态更新 {{ date(updatedAt, true) }}</span>
        </div>
        <div class="learning-runtime">
          <div class="runtime-main">
            <span class="runtime-label">正在学习 · 日志确认</span>
            <div v-if="activeTitles.length" class="active-course-titles">
              <strong v-for="title in activeTitles" :key="title">{{ title }}</strong>
            </div>
            <strong v-else class="runtime-waiting">{{
              runningIntent ? '等待课程活动输出' : '等待开始学习'
            }}</strong>
            <p class="runtime-message">{{ data.message || '勾选课程后即可开始学习。' }}</p>
          </div>
          <div class="runtime-selection">
            <span class="runtime-label"
              >本轮执行课程 · {{ data.running_course_titles.length }} 门</span
            >
            <p>{{ data.running_course_titles.join('、') || '开始后显示本轮课程范围' }}</p>
          </div>
        </div>
        <div v-if="data.latest_activity" class="latest-activity">
          <div>
            <span class="runtime-label">最新原始活动</span
            ><time>{{ date(data.latest_activity.created_at) }}</time>
          </div>
          <p>{{ data.latest_activity.message }}</p>
        </div>
        <div class="learning-controls">
          <NButton
            v-if="canPause"
            :disabled="blocked"
            :loading="busy === 'pause'"
            @click="action('pause')"
            ><template #icon><Pause :size="15" /></template>暂停学习</NButton
          >
          <NButton
            v-else
            type="primary"
            :disabled="
              blocked ||
              !selectedCount ||
              unavailableSelection ||
              !!missingSelection.length ||
              ['pausing', 'stopping'].includes(data.state)
            "
            :loading="busy === 'start' || busy === 'resume' || preparing"
            @click="prepare(data.desired_state === 'paused' ? 'resume' : 'start')"
            ><template #icon><Play :size="15" /></template
            >{{ data.desired_state === 'paused' ? '继续学习' : '开始学习' }}</NButton
          >
          <NButton
            :disabled="blocked || !canStop"
            :loading="busy === 'stop'"
            @click="action('stop')"
            ><template #icon><Square :size="14" /></template>停止学习</NButton
          >
          <span class="runtime-worker"
            ><span class="status-dot" :class="{ online: data.worker_online }" />{{
              data.worker_online ? '后台服务在线' : '后台服务离线'
            }}</span
          >
        </div>
        <NAlert v-if="!data.worker_online" type="warning" class="runtime-alert"
          >后台服务离线，请启动后台服务，再继续学习。课程选择可保存。</NAlert
        >
        <p v-if="rules" class="rules-summary">
          {{ overridden ? '账号专属规则' : '跟随默认规则' }} · {{ videoLabels[rules.video_mode] }} ·
          {{ answerLabels[rules.answer_mode]
          }}<template v-if="rules.answer_mode !== 'off' && paperTypes(rules)">
            · {{ paperTypes(rules) }} ·
            {{
              rules.submit_mode === 'save'
                ? '保存答案'
                : rules.submit_mode === 'complete'
                  ? '章测无空题时交卷'
                  : '答题后交卷'
            }}<template v-if="rules.submit_mode === 'complete' && (rules.work || rules.exam)"
              >；作业和考试自动交卷</template
            ></template
          >
        </p>
      </section>

      <section class="panel learning-courses" aria-labelledby="learning-courses-title">
        <div class="panel-heading course-panel-heading">
          <div>
            <h2 id="learning-courses-title">
              课程列表<span class="count-badge">{{ data.courses.length }}</span>
            </h2>
            <p class="muted">平台进度按已确认完成的章节计算，显示最近一次同步结果。</p>
          </div>
          <NButton
            :disabled="blocked || data.refresh_pending"
            :loading="data.refresh_pending || busy === 'refresh'"
            @click="action('refresh')"
            ><template #icon><RefreshCw :size="15" /></template
            >{{ data.refresh_pending ? '同步中' : '刷新课程与进度' }}</NButton
          >
        </div>
        <NAlert v-if="data.refresh_error" type="warning" class="course-alert"
          >{{ data.refresh_error
          }}<NButton text :disabled="blocked || data.refresh_pending" @click="action('refresh')"
            >重新同步</NButton
          ></NAlert
        >
        <NAlert v-else-if="data.refresh_pending" type="info" class="course-alert"
          >正在读取平台课程和章节，完成后更新进度。</NAlert
        >
        <div class="course-selection-tools">
          <NInput
            v-model:value="search"
            clearable
            placeholder="搜索课程或教师"
            aria-label="搜索账号课程"
            ><template #prefix><Search :size="15" /></template
          ></NInput>
          <label class="course-checkbox-label"
            ><input
              type="checkbox"
              :checked="allVisibleSelected"
              :indeterminate="someVisibleSelected"
              :disabled="blocked || !selectableCourses.length"
              @change="toggleVisible(($event.target as HTMLInputElement).checked)"
            /><span>{{ search ? '选择搜索结果' : '全选课程' }}</span></label
          >
          <NButton text :disabled="blocked || !selectedCount" @click="selection = []"
            >清空选择</NButton
          >
        </div>
        <div
          v-if="visibleCourses.length"
          class="learning-course-list"
          role="list"
          aria-label="可选择的学习课程"
        >
          <article
            v-for="course in visibleCourses"
            :key="course.id"
            class="learning-course-row"
            :class="{ selected: selection.includes(course.id) }"
            role="listitem"
          >
            <label class="course-pick"
              ><input
                type="checkbox"
                :checked="selection.includes(course.id)"
                :disabled="
                  blocked || (course.available === false && !selection.includes(course.id))
                "
                @change="toggleCourse(course.id, ($event.target as HTMLInputElement).checked)"
              /><span class="course-name"
                ><strong>{{ course.title }}</strong
                ><small
                  >{{ course.teacher || '教师信息待同步'
                  }}<span v-if="course.available === false">当前账号已无此课程</span
                  ><span v-if="activeTitles.includes(course.title)" class="course-live"
                    ><span class="status-dot online" />正在学习</span
                  ></small
                ></span
              ></label
            >
            <div class="course-platform-progress">
              <div class="course-progress-label">
                <span>平台章节进度</span
                ><strong>{{
                  course.progress === null ? '待同步' : `${Math.round(course.progress)}%`
                }}</strong>
              </div>
              <div
                class="course-progress-track"
                :aria-label="
                  course.progress === null
                    ? '章节进度待同步'
                    : `已完成 ${course.confirmed_chapters} 章，共 ${course.chapter_count} 章`
                "
              >
                <span :style="{ width: `${progress(course.progress || 0)}%` }" />
              </div>
              <small>{{
                course.progress === null
                  ? '同步后显示完成情况'
                  : `${course.confirmed_chapters} / ${course.chapter_count} 章已确认完成`
              }}</small>
            </div>
            <div class="course-sync-info">
              <small>进度同步 {{ date(course.progress_synced_at, true) }}</small
              ><NButton size="small" quaternary @click="openChapters(course)"
                ><template #icon><BookOpen :size="14" /></template>章节明细</NButton
              >
            </div>
          </article>
        </div>
        <EmptyState
          v-else
          :title="
            search
              ? '没有匹配的课程'
              : data.refresh_pending
                ? '正在同步账号课程'
                : '课程将在同步后显示'
          "
          :description="
            search ? '调整搜索内容，查看其他课程。' : '同步完成后，在这里勾选想学习的课程。'
          "
        />
        <div class="course-save-bar">
          <div>
            <strong>已选 {{ selectedCount }} 门课程</strong
            ><span v-if="dirty" class="selection-unsaved">有待保存的修改</span
            ><span v-else class="muted">选择已保存</span>
            <p v-if="!selectedCount && dirty">保存空选择会停止该账号的学习。</p>
            <p v-else-if="settingsPending">学习规则已保存，应用后用于当前学习安排。</p>
            <p v-else>
              {{
                runningIntent
                  ? '保存后，后台会按当前选择继续学习。'
                  : '课程选择会保留，下次进入可继续使用。'
              }}
            </p>
          </div>
          <div class="course-save-actions">
            <NButton v-if="dirty" :disabled="blocked" @click="restore">还原选择</NButton
            ><NButton
              type="primary"
              :disabled="
                blocked || (!dirty && !settingsPending && !conflict) || !!missingSelection.length
              "
              :loading="busy === 'save'"
              @click="prepare('save')"
              ><template #icon><Save :size="15" /></template
              >{{ runningIntent ? '保存并应用' : '保存选择' }}</NButton
            >
          </div>
        </div>
        <NAlert v-if="missingSelection.length" type="warning" class="course-alert"
          >部分勾选课程已从平台课程列表移除，请重新选择后保存。<NButton
            text
            :disabled="blocked"
            @click="selection = selection.filter((id) => !missingSelection.includes(id))"
            >移除失效选择</NButton
          ></NAlert
        >
      </section>
      <AccountLogs :key="accountId" :account-id="accountId" />
    </template>

    <NDrawer v-model:show="showRules" :width="'min(680px, 100vw)'"
      ><NDrawerContent title="账号学习规则" closable
        ><LearningRulesPanel
          v-if="showRules"
          :key="accountId"
          :account-id="accountId"
          managed-account
          @saved="rulesSaved" /></NDrawerContent
    ></NDrawer>
    <NDrawer
      :show="!!chapterCourse"
      :width="'min(680px, 100vw)'"
      @update:show="
        (value) => {
          if (!value) chapterCourse = null
        }
      "
      ><NDrawerContent :title="chapterCourse?.title || '章节明细'" closable
        ><NSpin :show="chapterLoading"
          ><NAlert v-if="chapterError" type="error">{{ chapterError }}</NAlert>
          <p class="muted">
            平台章节确认状态 · 同步于 {{ date(chapterCourse?.progress_synced_at) }}
          </p>
          <div v-for="chapter in chapters" :key="chapter.id" class="chapter-progress-row">
            <CheckCheck v-if="chapter.confirmed" :size="18" class="chapter-confirmed" /><BookOpen
              v-else
              :size="18"
            />
            <div>
              <strong>{{ chapter.title }}</strong
              ><small
                >{{ chapter.confirmed ? '平台已确认完成' : chapter.locked ? '待解锁' : '待完成' }} ·
                {{ chapter.job_count }} 个任务点</small
              >
            </div>
          </div>
          <EmptyState
            v-if="!chapterLoading && !chapters.length && !chapterError"
            title="章节明细待同步"
            description="使用账号页的「刷新课程与进度」读取最新章节。" /></NSpin></NDrawerContent
    ></NDrawer>
    <NModal
      :show="!!review"
      preset="card"
      title="确认自动交卷范围"
      class="form-modal"
      @update:show="
        (value) => {
          if (!value) review = null
        }
      "
      ><template v-if="review"
        ><NAlert type="warning" class="mb-20"
          >本次学习允许对 {{ paperTypes(review.rules) }} 自动交卷，请确认课程与答题设置。</NAlert
        >
        <p>
          {{ answerLabels[review.rules.answer_mode] }} ·
          {{ review.rules.submit_mode === 'complete' ? '章测无空题时交卷' : '答题后交卷' }}
        </p>
        <p
          v-if="review.rules.submit_mode === 'complete' && (review.rules.work || review.rules.exam)"
        >
          课程作业和考试按自动交卷方式执行。
        </p>
        <ul class="submit-review-courses">
          <li v-for="(title, index) in review.courses" :key="index">{{ title }}</li>
        </ul>
        <NSpace justify="end"
          ><NButton @click="review = null">返回检查</NButton
          ><NButton type="primary" @click="confirmReview"
            >确认并{{ review.kind === 'save' ? '应用' : '开始学习' }}</NButton
          ></NSpace
        ></template
      ></NModal
    >
  </div>
</template>

<style scoped>
.account-learning {
  min-width: 0;
}
.account-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 18px;
}
.account-initial-loading {
  display: block;
  margin: 60px auto;
  text-align: center;
}
.learning-status,
.learning-courses {
  margin-bottom: 22px;
}
.learning-status {
  padding: 22px;
}
.learning-status-top,
.learning-status-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.learning-status-top {
  justify-content: space-between;
  flex-wrap: wrap;
}
.learning-status-title h2 {
  margin: 0;
  font-size: 15px;
}
.status-updated {
  font-size: 11px;
}
.learning-runtime {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 30px;
  padding: 23px 0 18px;
}
.runtime-label {
  display: block;
  color: var(--soft-text);
  font-size: 11px;
  margin-bottom: 7px;
}
.active-course-titles {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 18px;
  overflow-wrap: anywhere;
}
.runtime-waiting {
  font-size: 17px;
  font-weight: 500;
}
.runtime-message {
  color: var(--soft-text);
  margin: 9px 0 0;
  overflow-wrap: anywhere;
}
.runtime-selection {
  border-left: 1px solid var(--border);
  padding-left: 24px;
}
.runtime-selection p {
  margin: 0;
  line-height: 1.9;
  overflow-wrap: anywhere;
}
.latest-activity {
  padding: 13px 15px;
  background: var(--hover);
  border-radius: 8px;
  margin-bottom: 18px;
}
.latest-activity > div {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  flex-wrap: wrap;
}
.latest-activity time {
  color: var(--soft-text);
  font-size: 11px;
}
.latest-activity p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: Consolas, 'Microsoft YaHei', monospace;
  font-size: 12px;
}
.learning-controls {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.runtime-worker {
  margin-left: auto;
  font-size: 12px;
  color: var(--soft-text);
  display: inline-flex;
  gap: 7px;
  align-items: center;
}
.runtime-alert {
  margin-top: 14px;
}
.rules-summary {
  margin: 16px 0 0;
  color: var(--soft-text);
  font-size: 12px;
}
.course-panel-heading {
  flex-wrap: wrap;
  gap: 16px;
}
.course-panel-heading p {
  font-size: 12px;
  margin: 7px 0 0;
}
.course-alert {
  margin: 12px 18px;
}
.course-selection-tools {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.course-selection-tools .n-input {
  max-width: 330px;
}
.course-checkbox-label,
.course-pick {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}
input[type='checkbox'] {
  width: 18px;
  height: 18px;
  accent-color: var(--accent);
  flex-shrink: 0;
  cursor: pointer;
  margin: 0;
}
input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 4px;
}
.learning-course-row {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(160px, 0.8fr) minmax(140px, 0.7fr);
  gap: 24px;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--border);
}
.learning-course-row.selected {
  background: var(--accent-soft);
}
.course-pick {
  min-width: 0;
  padding: 4px 0;
}
.course-name {
  min-width: 0;
}
.course-name strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.course-name small {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--soft-text);
  margin-top: 7px;
}
.course-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
}
.course-progress-label {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 11px;
  color: var(--soft-text);
}
.course-progress-label strong {
  color: var(--text);
}
.course-progress-track {
  height: 5px;
  background: var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0;
}
.course-progress-track span {
  display: block;
  height: 100%;
  background: var(--accent);
}
.course-platform-progress small,
.course-sync-info small {
  color: var(--soft-text);
  font-size: 11px;
}
.course-sync-info {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.course-save-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  background: var(--panel);
  border-radius: 0 0 10px 10px;
}
.course-save-bar strong {
  margin-right: 14px;
}
.course-save-bar p {
  margin: 5px 0 0;
  color: var(--soft-text);
  font-size: 12px;
}
.selection-unsaved {
  color: var(--accent);
  font-size: 12px;
}
.course-save-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.chapter-progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 0;
  border-bottom: 1px solid var(--border);
}
.chapter-progress-row strong {
  display: block;
  overflow-wrap: anywhere;
}
.chapter-progress-row small {
  display: block;
  margin-top: 6px;
  color: var(--soft-text);
}
.chapter-confirmed {
  color: #16a34a;
}
.submit-review-courses {
  padding-left: 22px;
  max-height: 230px;
  overflow: auto;
  margin-bottom: 24px;
}
.submit-review-courses li {
  padding: 5px 0;
  overflow-wrap: anywhere;
}
@media (max-width: 760px) {
  .learning-status {
    padding: 18px 16px;
  }
  .learning-runtime {
    grid-template-columns: 1fr;
    gap: 18px;
    padding: 20px 0;
  }
  .runtime-selection {
    padding-left: 0;
    border-left: 0;
  }
  .learning-course-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 14px 18px;
    padding: 18px 16px;
  }
  .course-pick {
    grid-column: 1 / -1;
  }
  .course-platform-progress {
    margin-left: 30px;
    min-width: 0;
  }
  .course-sync-info {
    max-width: 140px;
    text-align: right;
  }
  .course-save-bar {
    flex-wrap: wrap;
    padding: 16px;
  }
  .course-save-actions {
    width: 100%;
    justify-content: flex-end;
  }
  .course-selection-tools {
    padding: 14px 16px;
    gap: 16px;
  }
  .course-selection-tools .n-input {
    max-width: none;
    width: 100%;
  }
  .course-checkbox-label {
    min-height: 30px;
  }
  .runtime-worker {
    width: 100%;
    margin: 4px 0 0;
  }
}
@media (max-width: 390px) {
  .learning-course-row {
    gap: 12px;
  }
  .course-platform-progress {
    margin-left: 0;
  }
  .course-sync-info {
    max-width: 118px;
  }
}
</style>
