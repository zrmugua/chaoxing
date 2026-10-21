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
  NSwitch,
  NSpin,
  useMessage,
} from 'naive-ui'
import { api, errorText } from '../api'
const message = useMessage()
const loading = ref(true),
  saving = ref(false),
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
    rest.sender = rest.username
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
        </div>
        <NFormItem label="收件邮箱"><NDynamicTags v-model:value="form.recipients" /></NFormItem>
        <p class="settings-note">运行邮件由 Console 发送，内容与时机遵循原版行为。账号可单独设置收件邮箱。</p>
        <div class="settings-actions">
          <NButton
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
