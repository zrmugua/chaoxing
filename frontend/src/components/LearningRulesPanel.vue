<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NDynamicTags,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSwitch,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { api, errorText, post } from '../api'
import type { Course, StudySettings } from '../types'
const props = defineProps<{ accountId?: number }>()
const emit = defineEmits<{ start: [] }>()
const message = useMessage()
const loading = ref(true),
  saving = ref(false),
  error = ref(''),
  overridden = ref(false)
const courses = ref<Course[]>([]),
  proxyConfigured = ref(false),
  clearProxy = ref(false)
const preferences = reactive({ inform_emails: [] as string[], proxy_url: '' })
const form = reactive<StudySettings>({
  video_mode: 'normal',
  media_client: 'desktop',
  audio: true,
  document: true,
  read: true,
  hyperlink: true,
  chapter_test: true,
  shuffle: false,
  include_courses: [],
  exclude_courses: [],
  execution_timeout: 28800,
  node_concurrency: 2,
  work: false,
  exam: false,
  answer_mode: 'off',
  submit_mode: 'save',
})
const endpoint = computed(() =>
  props.accountId ? `/accounts/${props.accountId}/study-settings` : '/settings/study',
)
const courseOptions = computed(() =>
  courses.value.map((c) => ({ label: `${c.title} · ${c.remote_id}`, value: c.remote_id })),
)
const scope = ref('all')
const scopeOptions = [
  { label: '全部课程', value: 'all' },
  { label: '仅学习所选课程', value: 'include' },
  { label: '排除所选课程', value: 'exclude' },
  { label: '同时设置包含与排除', value: 'custom' },
]
function changeScope(value: string) {
  if (value === 'all') {
    form.include_courses = []
    form.exclude_courses = []
  }
  if (value === 'include') form.exclude_courses = []
  if (value === 'exclude') form.include_courses = []
}
function assign(data: any) {
  Object.assign(form, props.accountId ? data.rules : data)
  overridden.value = Boolean(data.overridden)
  scope.value =
    form.include_courses.length && form.exclude_courses.length
      ? 'custom'
      : form.include_courses.length
        ? 'include'
        : form.exclude_courses.length
          ? 'exclude'
          : 'all'
}
async function load() {
  loading.value = true
  try {
    assign(await api(endpoint.value))
    if (props.accountId) {
      courses.value = (await api<Course[]>('/courses')).filter(
        (c) => c.account_id === props.accountId,
      )
      const data = await api<any>(`/accounts/${props.accountId}/preferences`)
      preferences.inform_emails = data.inform_emails
      proxyConfigured.value = data.proxy_configured
    }
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
async function sync() {
  try {
    await post(`/accounts/${props.accountId}/sync`)
    message.success('同步已加入队列，完成后刷新课程选项')
  } catch (e) {
    message.error(errorText(e))
  }
}
async function save(start = false) {
  if (
    (scope.value === 'include' && !form.include_courses.length) ||
    (scope.value === 'exclude' && !form.exclude_courses.length)
  ) {
    message.warning('请先选择课程，或将课程模式设为全部课程')
    return
  }
  saving.value = true
  try {
    if (props.accountId) {
      const data = await api<any>(`/accounts/${props.accountId}/preferences`, {
        method: 'PUT',
        body: JSON.stringify({
          inform_emails: preferences.inform_emails,
          ...(clearProxy.value
            ? { proxy_url: '' }
            : preferences.proxy_url
              ? { proxy_url: preferences.proxy_url }
              : {}),
        }),
      })
      proxyConfigured.value = data.proxy_configured
      preferences.proxy_url = ''
      clearProxy.value = false
    }
    assign(await api(endpoint.value, { method: 'PUT', body: JSON.stringify(form) }))
    message.success('课程配置已保存')
    if (start) emit('start')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function reset() {
  try {
    assign(await api(endpoint.value, { method: 'DELETE' }))
    message.success('已使用全局课程配置')
  } catch (e) {
    message.error(errorText(e))
  }
}
onMounted(load)
</script>
<template>
  <section class="panel settings-panel">
    <div class="settings-heading">
      <div>
        <h2>
          课程配置
          <NTag v-if="accountId" size="small" :bordered="false">{{
            overridden ? '账号专属' : '使用全局'
          }}</NTag>
        </h2>
        <p>选择课程范围、视频方式和答题策略</p>
      </div>
    </div>
    <NAlert v-if="error" type="error" class="mb-20"
      >{{ error }} <NButton text @click="load">重试</NButton></NAlert
    >
    <NSpin :show="loading"
      ><NForm label-placement="top" @submit.prevent="save()">
        <NFormItem label="课程模式"
          ><NSelect v-model:value="scope" :options="scopeOptions" @update:value="changeScope"
        /></NFormItem>
        <NFormItem v-if="scope === 'include' || scope === 'custom'" label="仅学习这些课程"
          ><NSelect
            v-model:value="form.include_courses"
            multiple
            filterable
            tag
            clearable
            :options="courseOptions"
            placeholder="选择课程，或输入完整名称 / 编号"
        /></NFormItem>
        <NFormItem v-if="scope === 'exclude' || scope === 'custom'" label="排除这些课程"
          ><NSelect
            v-model:value="form.exclude_courses"
            multiple
            filterable
            tag
            clearable
            :options="courseOptions"
            placeholder="选择要排除的课程"
        /></NFormItem>
        <div v-if="accountId" class="row-actions mb-20">
          <NButton size="small" @click="sync">同步账号课程</NButton
          ><NButton size="small" @click="load">刷新课程选项</NButton
          ><span class="muted">已同步 {{ courses.length }} 门课程</span>
        </div>
        <div class="settings-fields">
          <NFormItem label="视频模式"
            ><NSelect
              v-model:value="form.video_mode"
              :options="[
                { label: '不看视频', value: 'off' },
                { label: '普通模式', value: 'normal' },
                { label: '多课程同时进行', value: 'multi_course' },
                { label: '多任务点同时进行', value: 'multi_node' },
              ]"
          /></NFormItem>
          <NFormItem v-if="form.video_mode === 'multi_node'" label="同时任务点数量"
            ><NInputNumber v-model:value="form.node_concurrency" :min="1" :max="7" :precision="0"
          /></NFormItem>
          <NFormItem label="自动答题模式"
            ><NSelect
              v-model:value="form.answer_mode"
              :options="[
                { label: '关闭自动答题', value: 'off' },
                { label: 'AI 大模型自动答题', value: 'ai' },
                { label: '外置题库答题', value: 'question_bank' },
                { label: '学习通内置 AI 答题', value: 'chaoxing_ai' },
              ]"
          /></NFormItem>
          <NFormItem v-if="form.answer_mode !== 'off'" label="答题提交方式"
            ><NSelect
              v-model:value="form.submit_mode"
              :options="[
                { label: '不交卷，只保存', value: 'save' },
                { label: '答题后直接交卷', value: 'submit' },
                { label: '无空题时交卷', value: 'complete' },
              ]"
          /></NFormItem>
        </div>
        <div v-if="form.answer_mode !== 'off'" class="settings-fields">
          <NFormItem label="章节测验"
            ><NSwitch v-model:value="form.chapter_test" aria-label="章节测验"
          /></NFormItem>
          <NFormItem label="课程作业"
            ><NSwitch v-model:value="form.work" aria-label="课程作业"
          /></NFormItem>
          <NFormItem label="课程考试"
            ><NSwitch v-model:value="form.exam" aria-label="课程考试"
          /></NFormItem>
        </div>
        <NAlert
          v-if="form.answer_mode !== 'off'"
          :type="form.submit_mode === 'save' ? 'info' : 'warning'"
          class="mb-20"
        >
          {{
            form.submit_mode === 'save'
              ? '任务会保存匹配到的答案，试卷交卷由你在学习通完成。'
              : '本配置允许自动交卷，启动前请核对课程范围和答题服务。'
          }}
          遇到验证码、人脸或平台限制时，任务会等待人工处理。
        </NAlert>
        <NCollapse
          ><NCollapseItem title="学习内容与执行参数" name="advanced"
            ><div class="settings-fields">
              <NFormItem
                v-for="item in [
                  ['audio', '音频'],
                  ['document', '文档'],
                  ['read', '阅读'],
                  ['hyperlink', '外链'],
                  ['shuffle', '随机学习顺序'],
                ] as const"
                :key="item[0]"
                :label="item[1]"
                ><NSwitch v-model:value="form[item[0]]" :aria-label="item[1]"
              /></NFormItem>
              <NFormItem label="上报客户端"
                ><NSelect
                  v-model:value="form.media_client"
                  :options="[
                    { label: '电脑端', value: 'desktop' },
                    { label: '移动端', value: 'mobile' },
                  ]"
              /></NFormItem>
              <NFormItem label="任务点执行时限（秒）"
                ><NInputNumber
                  v-model:value="form.execution_timeout"
                  :min="30"
                  :max="86400"
                  :precision="0"
              /></NFormItem></div
          ></NCollapseItem>
          <NCollapseItem v-if="accountId" title="账号通知与网络" name="account">
            <NFormItem label="通知邮箱"
              ><div class="setting-field">
                <NDynamicTags v-model:value="preferences.inform_emails" />
                <p>留空使用系统收件人，需要先在系统设置中启用邮件。</p>
              </div></NFormItem
            >
            <NFormItem label="账号 HTTP / HTTPS 代理"
              ><NInput
                v-model:value="preferences.proxy_url"
                type="password"
                show-password-on="click"
                autocomplete="new-password"
                :placeholder="
                  proxyConfigured ? '已配置，留空保留' : 'http://主机:端口，可包含代理授权'
                "
            /></NFormItem>
            <NFormItem v-if="proxyConfigured" label="清除已保存代理"
              ><NSwitch v-model:value="clearProxy" aria-label="清除已保存代理"
            /></NFormItem> </NCollapseItem
        ></NCollapse>
        <p class="settings-note">
          课程排除优先。新建任务保存配置快照，已有任务继续使用创建时的配置。完成状态以学习通回读结果为准。
        </p>
        <div class="settings-actions">
          <NButton v-if="accountId && overridden" :disabled="saving" @click="reset"
            >使用全局配置</NButton
          ><NButton attr-type="submit" :loading="saving" :disabled="loading || !!error"
            >保存配置</NButton
          ><NButton
            v-if="accountId"
            type="primary"
            :loading="saving"
            :disabled="loading || !!error"
            @click="save(true)"
            >保存并准备启动</NButton
          >
        </div>
      </NForm></NSpin
    >
  </section>
</template>
