<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NSwitch, NSpin, useMessage } from 'naive-ui'
import { api, errorText, post } from '../api'
const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const configured = ref(false)
const error = ref('')
const question = ref('')
const answer = ref('')
const form = reactive({ enabled: false, url: '', token: '', ai_fallback: false, allow_lan: false })
async function load() {
  try {
    const data = await api<any>('/settings/question-bank')
    Object.assign(form, {
      enabled: data.enabled,
      url: data.url,
      ai_fallback: data.ai_fallback,
      allow_lan: data.allow_lan,
    })
    configured.value = data.secret_configured
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
async function save() {
  saving.value = true
  try {
    const { token, ...rest } = form
    const data = await api<any>('/settings/question-bank', {
      method: 'PUT',
      body: JSON.stringify({ ...rest, ...(token ? { token } : {}) }),
    })
    configured.value = data.secret_configured
    form.token = ''
    message.success('题库配置已保存')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function test() {
  testing.value = true
  answer.value = ''
  try {
    const data = await post<{ answer: string; source: string }>('/answers/preview', {
      question: question.value,
      options: [],
    })
    answer.value = `${data.source === 'question_bank' ? '题库' : 'AI'}：${data.answer}`
  } catch (e) {
    message.error(errorText(e))
  } finally {
    testing.value = false
  }
}
onMounted(load)
</script>
<template>
  <section class="panel settings-panel">
    <div class="settings-heading">
      <div>
        <h2>题库接口</h2>
        <p>Yatori 自定义题库协议，可配置 AI 回退</p>
      </div>
      <NSwitch v-model:value="form.enabled" aria-label="启用题库" />
    </div>
    <NAlert v-if="error" type="error" class="mb-20">{{ error }}</NAlert>
    <NSpin :show="loading"
      ><NForm label-placement="top" @submit.prevent="save">
        <NFormItem label="查询接口地址"
          ><NInput
            v-model:value="form.url"
            placeholder="https://example.com/query"
            :disabled="!form.enabled"
        /></NFormItem>
        <NFormItem label="授权 Token"
          ><NInput
            v-model:value="form.token"
            type="password"
            show-password-on="click"
            :placeholder="configured ? '已配置，留空保留' : '接口需要授权时填写'"
            autocomplete="new-password"
            :disabled="!form.enabled"
        /></NFormItem>
        <NFormItem label="题库无结果时使用 AI"
          ><NSwitch v-model:value="form.ai_fallback" :disabled="!form.enabled" aria-label="AI 回退"
        /></NFormItem>
        <NFormItem label="使用本机或局域网题库"
          ><NSwitch
            v-model:value="form.allow_lan"
            :disabled="!form.enabled"
            aria-label="使用本机或局域网题库"
        /></NFormItem>
        <p class="settings-note">
          接口接收题目类型、正文和选项，支持 answers / answer 返回格式。Token
          加密保存。答案预览与自动答题共用此服务，保存和交卷按课程配置执行。
        </p>
        <div class="settings-actions">
          <NButton
            type="primary"
            attr-type="submit"
            :loading="saving"
            :disabled="loading || !!error"
            >保存题库配置</NButton
          >
        </div>
      </NForm>
      <NForm label-placement="top" @submit.prevent="test"
        ><NFormItem label="连接测试题目"
          ><NInput v-model:value="question" placeholder="输入要查询的题目" /></NFormItem
        ><NButton attr-type="submit" :loading="testing" :disabled="!question.trim()"
          >查询已保存的答案服务</NButton
        ><NAlert v-if="answer" type="info" class="mt-16">{{ answer }}</NAlert></NForm
      ></NSpin
    >
  </section>
</template>
