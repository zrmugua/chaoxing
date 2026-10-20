<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  NAlert,
  NButton,
  NDynamicTags,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSwitch,
  NSpin,
  useMessage,
} from 'naive-ui'
import { api, errorText, post } from '../api'
const message = useMessage()
const loading = ref(true),
  saving = ref(false),
  testing = ref(false),
  configured = ref(false)
const error = ref('')
const form = reactive({
  enabled: false,
  host: '',
  port: 465,
  security: 'ssl',
  username: '',
  password: '',
  sender: '',
  recipients: [] as string[],
  on_success: true,
  on_failure: true,
  on_attention: true,
})
const events = [
  { key: 'on_success', label: '任务完成' },
  { key: 'on_failure', label: '任务失败' },
  { key: 'on_attention', label: '需要人工处理' },
] as const
async function load() {
  try {
    const data = await api<any>('/settings/email')
    const { secret_configured, ...rest } = data
    Object.assign(form, rest)
    configured.value = secret_configured
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
async function save() {
  saving.value = true
  try {
    const { password, ...rest } = form
    const data = await api<any>('/settings/email', {
      method: 'PUT',
      body: JSON.stringify({ ...rest, ...(password ? { password } : {}) }),
    })
    configured.value = data.secret_configured
    form.password = ''
    message.success('邮件配置已保存')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function test() {
  testing.value = true
  try {
    await post('/settings/email/test')
    message.success('测试邮件已发送')
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
        <h2>邮件通知</h2>
        <p>通过 SMTP 接收学习任务结果</p>
      </div>
      <NSwitch v-model:value="form.enabled" aria-label="启用邮件通知" />
    </div>
    <NAlert v-if="error" type="error" class="mb-20">{{ error }}</NAlert
    ><NSpin :show="loading"
      ><NForm label-placement="top" @submit.prevent="save">
        <div class="settings-fields">
          <NFormItem label="SMTP 服务器"
            ><NInput v-model:value="form.host" placeholder="smtp.example.com"
          /></NFormItem>
          <NFormItem label="端口"
            ><NInputNumber v-model:value="form.port" :min="1" :max="65535" :precision="0"
          /></NFormItem>
          <NFormItem label="连接加密"
            ><NSelect
              v-model:value="form.security"
              :options="[
                { label: 'SSL / TLS', value: 'ssl' },
                { label: 'STARTTLS', value: 'starttls' },
              ]"
          /></NFormItem>
          <NFormItem label="SMTP 用户名"
            ><NInput v-model:value="form.username" autocomplete="off"
          /></NFormItem>
          <NFormItem label="邮箱密码 / 授权码"
            ><NInput
              v-model:value="form.password"
              type="password"
              show-password-on="click"
              :placeholder="configured ? '已配置，留空保留' : '输入授权码'"
              autocomplete="new-password"
          /></NFormItem>
          <NFormItem label="发件邮箱"
            ><NInput v-model:value="form.sender" placeholder="me@example.com"
          /></NFormItem>
        </div>
        <NFormItem label="收件邮箱"><NDynamicTags v-model:value="form.recipients" /></NFormItem>
        <div class="settings-fields">
          <NFormItem v-for="event in events" :key="event.key" :label="event.label"
            ><NSwitch v-model:value="form[event.key]" :aria-label="event.label"
          /></NFormItem>
        </div>
        <p class="settings-note">通知仅包含任务编号、状态和处理结果。授权码及邮箱配置加密保存。</p>
        <div class="settings-actions">
          <NButton :loading="testing" :disabled="!form.enabled" @click="test">发送测试邮件</NButton
          ><NButton
            type="primary"
            attr-type="submit"
            :loading="saving"
            :disabled="loading || !!error"
            >保存邮件配置</NButton
          >
        </div>
      </NForm></NSpin
    >
  </section>
</template>
