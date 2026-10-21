<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NSwitch, NSpin, useMessage } from 'naive-ui'
import { api, errorText } from '../api'
const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const configured = ref(false)
const error = ref('')
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
onMounted(load)
</script>
<template>
  <section class="panel settings-panel">
    <div class="settings-heading">
      <div>
        <h2>题库接口</h2>
        <p>配置原版 Console 的外置题库地址</p>
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
        <NFormItem label="使用本机或局域网题库"
          ><NSwitch
            v-model:value="form.allow_lan"
            :disabled="!form.enabled"
            aria-label="使用本机或局域网题库"
        /></NFormItem>
        <p class="settings-note">地址写入 Console 的 apiQueSetting.url，题库服务需兼容原版 Console 协议。</p>
        <div class="settings-actions">
          <NButton
            type="primary"
            attr-type="submit"
            :loading="saving"
            :disabled="loading || !!error"
            >保存题库配置</NButton
          >
        </div>
      </NForm></NSpin
    >
  </section>
</template>
