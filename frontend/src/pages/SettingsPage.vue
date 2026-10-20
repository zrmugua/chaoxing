<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSpin,
  NSwitch,
  NTag,
  NSelect,
  NTabs,
  NTabPane,
  useMessage,
} from 'naive-ui'
import { Bot, Gauge, KeyRound, Save } from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import LearningRulesPanel from '../components/LearningRulesPanel.vue'
import QuestionBankSettingsPanel from '../components/QuestionBankSettingsPanel.vue'
import EmailSettingsPanel from '../components/EmailSettingsPanel.vue'
import ConfigurationPanel from '../components/ConfigurationPanel.vue'
import { api, errorText } from '../api'
import type { Settings } from '../types'

const message = useMessage()
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const savingAI = ref(false)
const form = reactive({
  concurrency: 1,
  retry_seconds: 30,
  max_attempts: 3,
  log_retention_days: 30,
  log_level: 'info',
  completion_tone: false,
  color_log: true,
  log_out_file: false,
})
const ai = reactive({ enabled: false, base_url: '', model: '', api_key: '', api_style: 'chat' })
const keyConfigured = ref(false)
const provider = ref('custom')
const providers = [
  {
    label: '秘塔 AI',
    value: 'metaso',
    url: 'https://metaso.cn/api/v1',
    model: 'fast',
    style: 'metaso',
  },
  { label: '自定义兼容接口', value: 'custom', url: '', model: '', style: 'chat' },
  {
    label: 'OpenAI',
    value: 'openai',
    url: 'https://api.openai.com/v1',
    model: '',
    style: 'responses',
  },
  {
    label: 'DeepSeek',
    value: 'deepseek',
    url: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    style: 'chat',
  },
  {
    label: '通义千问',
    value: 'qwen',
    url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-plus-latest',
    style: 'chat',
  },
  {
    label: '智谱 GLM',
    value: 'glm',
    url: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-4',
    style: 'chat',
  },
  {
    label: '讯飞星火',
    value: 'spark',
    url: 'https://spark-api-open.xf-yun.com/v1',
    model: 'generalv3.5',
    style: 'chat',
  },
  {
    label: '豆包',
    value: 'doubao',
    url: 'https://ark.cn-beijing.volces.com/api/v3',
    model: '',
    style: 'chat',
  },
  {
    label: '硅基流动',
    value: 'silicon',
    url: 'https://api.siliconflow.cn/v1',
    model: '',
    style: 'chat',
  },
]
function applyProvider(value: string) {
  const preset = providers.find((item) => item.value === value)
  if (preset?.url) {
    ai.base_url = preset.url
    ai.model = preset.model
    ai.api_style = preset.style
  }
}
function assign(data: Settings) {
  Object.assign(form, {
    concurrency: data.concurrency,
    retry_seconds: data.retry_seconds,
    max_attempts: data.max_attempts,
    log_retention_days: data.log_retention_days,
    log_level: data.log_level,
    completion_tone: data.completion_tone,
    color_log: data.color_log,
    log_out_file: data.log_out_file,
  })
  if (data.ai) {
    ai.enabled = data.ai.enabled
    ai.base_url = data.ai.base_url
    ai.model = data.ai.model
    ai.api_style = data.ai.api_style
    keyConfigured.value = data.ai.key_configured
  }
}
async function load() {
  loading.value = true
  try {
    assign(await api<Settings>('/settings'))
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
async function save() {
  saving.value = true
  try {
    await api('/settings', { method: 'PUT', body: JSON.stringify(form) })
    message.success('运行设置已保存')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function saveAI() {
  if (
    ai.enabled &&
    (!ai.base_url.trim() || !ai.model.trim() || (!keyConfigured.value && !ai.api_key))
  ) {
    message.warning('请填写 API 地址、模型名称和 API Key')
    return
  }
  savingAI.value = true
  try {
    await api('/settings/ai', {
      method: 'PUT',
      body: JSON.stringify({
        enabled: ai.enabled,
        base_url: ai.base_url.trim(),
        model: ai.model.trim(),
        api_style: ai.api_style,
        ...(ai.api_key ? { api_key: ai.api_key } : {}),
      }),
    })
    if (ai.api_key) keyConfigured.value = true
    ai.api_key = ''
    message.success('AI 接口配置已保存')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    savingAI.value = false
  }
}
onMounted(() => void load())
</script>

<template>
  <PageHeading
    title="系统设置"
    description="配置学习规则、运行参数、答题服务与通知。"
    eyebrow="SETTINGS"
  />
  <NAlert v-if="error" type="error" class="mb-20">
    {{ error }}<NButton size="small" text @click="load">重试</NButton>
  </NAlert>
  <NTabs type="segment" animated>
    <NTabPane name="study" tab="课程配置"><LearningRulesPanel /></NTabPane>
    <NTabPane name="runtime" tab="运行与 AI">
      <NSpin :show="loading">
        <div class="settings-grid">
          <section class="panel settings-panel">
            <div class="settings-heading">
              <div class="setting-icon"><Gauge :size="20" /></div>
              <div>
                <h2>运行设置</h2>
                <p>配置任务并发、重试与日志保留</p>
              </div>
            </div>
            <NForm label-placement="top" @submit.prevent="save">
              <div class="settings-fields">
                <NFormItem label="浏览器完成提示音"
                  ><div class="setting-field">
                    <NSwitch v-model:value="form.completion_tone" aria-label="浏览器完成提示音" />
                    <p>页面打开且浏览器允许播放音频时生效。</p>
                  </div></NFormItem
                >
                <NFormItem label="彩色日志"
                  ><NSwitch v-model:value="form.color_log" aria-label="彩色日志"
                /></NFormItem>
                <NFormItem label="日志输出到文件"
                  ><div class="setting-field">
                    <NSwitch v-model:value="form.log_out_file" aria-label="日志输出到文件" />
                    <p>保存至数据目录的 console.log，按大小轮换保留。</p>
                  </div></NFormItem
                >
                <NFormItem label="全局并发数">
                  <div class="setting-field">
                    <NInputNumber
                      v-model:value="form.concurrency"
                      :min="1"
                      :max="8"
                      :precision="0"
                    />
                    <p>同时执行的课程或账号任务数，多课程模式允许同账号并行。</p>
                  </div>
                </NFormItem>
                <NFormItem label="重试等待时间">
                  <div class="setting-field">
                    <NInputNumber
                      v-model:value="form.retry_seconds"
                      :min="5"
                      :max="3600"
                      :precision="0"
                    >
                      <template #suffix>秒</template>
                    </NInputNumber>
                    <p>发生可重试错误后，等待指定时间再尝试。</p>
                  </div>
                </NFormItem>
                <NFormItem label="最大尝试次数">
                  <div class="setting-field">
                    <NInputNumber
                      v-model:value="form.max_attempts"
                      :min="1"
                      :max="5"
                      :precision="0"
                    />
                    <p>新任务的尝试上限，包含首次执行。</p>
                  </div>
                </NFormItem>
                <NFormItem label="日志保留时间">
                  <div class="setting-field">
                    <NInputNumber
                      v-model:value="form.log_retention_days"
                      :min="1"
                      :max="365"
                      :precision="0"
                    >
                      <template #suffix>天</template>
                    </NInputNumber>
                    <p>后台定期清理超过保留时间的系统日志。</p>
                  </div>
                </NFormItem>
                <NFormItem label="日志记录级别"
                  ><div class="setting-field">
                    <NSelect
                      v-model:value="form.log_level"
                      :options="[
                        { label: '调试信息', value: 'debug' },
                        { label: '信息及以上', value: 'info' },
                        { label: '警告及以上', value: 'warning' },
                        { label: '仅错误', value: 'error' },
                      ]"
                    />
                    <p>保存后实时生效，系统日志页可筛选并导出记录。</p>
                  </div></NFormItem
                >
              </div>
              <p class="settings-note">
                任务在服务器后台执行。请结合服务器资源与平台要求设置并发数。
              </p>
              <div class="settings-actions">
                <NButton
                  type="primary"
                  :loading="saving"
                  :disabled="loading || !!error"
                  attr-type="submit"
                >
                  <template #icon><Save :size="15" /></template>保存运行设置
                </NButton>
              </div>
            </NForm>
          </section>

          <section class="panel settings-panel">
            <div class="settings-heading">
              <div class="setting-icon"><Bot :size="20" /></div>
              <div>
                <h2>
                  AI 辅助接口<NTag size="small" :bordered="false" class="optional-tag">可选</NTag>
                </h2>
                <p>连接 OpenAI 兼容服务</p>
              </div>
              <NSwitch v-model:value="ai.enabled" :disabled="loading" aria-label="启用 AI 接口" />
            </div>
            <NForm label-placement="top" @submit.prevent="saveAI">
              <NFormItem label="服务预设"
                ><NSelect
                  v-model:value="provider"
                  :options="providers"
                  :disabled="!ai.enabled"
                  @update:value="applyProvider"
              /></NFormItem>
              <NFormItem label="API 地址">
                <NInput
                  v-model:value="ai.base_url"
                  placeholder="https://api.example.com/v1"
                  :disabled="!ai.enabled"
                />
              </NFormItem>
              <NFormItem label="模型名称">
                <NInput
                  v-model:value="ai.model"
                  placeholder="输入服务提供方的模型标识"
                  :disabled="!ai.enabled"
                />
              </NFormItem>
              <NFormItem label="API 协议"
                ><NSelect
                  v-model:value="ai.api_style"
                  :disabled="!ai.enabled"
                  :options="[
                    { label: 'Chat Completions', value: 'chat' },
                    { label: 'Responses', value: 'responses' },
                    { label: '秘塔 AI', value: 'metaso' },
                  ]"
              /></NFormItem>
              <NFormItem label="API Key">
                <div class="setting-field full-width">
                  <NInput
                    v-model:value="ai.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="keyConfigured ? '已配置，输入新密钥可替换' : '输入 API Key'"
                    :disabled="!ai.enabled"
                    autocomplete="new-password"
                  >
                    <template #prefix><KeyRound :size="15" /></template>
                  </NInput>
                  <p>
                    {{
                      keyConfigured
                        ? '密钥已保存，留空继续使用现有密钥。'
                        : '密钥加密保存，接口仅返回配置状态。'
                    }}
                  </p>
                </div>
              </NFormItem>
              <p class="settings-note">
                用于答案预览与课程自动答题，保存和交卷方式由课程配置控制。
              </p>
              <div class="settings-actions">
                <NButton
                  type="primary"
                  attr-type="submit"
                  :loading="savingAI"
                  :disabled="loading || !!error"
                >
                  <template #icon><Save :size="15" /></template>保存 AI 配置
                </NButton>
              </div>
            </NForm>
          </section>
        </div>
      </NSpin>
    </NTabPane>
    <NTabPane name="bank" tab="题库"><QuestionBankSettingsPanel /></NTabPane>
    <NTabPane name="email" tab="邮件通知"><EmailSettingsPanel /></NTabPane>
    <NTabPane name="configuration" tab="配置文件"><ConfigurationPanel @imported="load" /></NTabPane>
  </NTabs>
</template>
