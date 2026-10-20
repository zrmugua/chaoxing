<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NInput, NSpace, NSwitch, useMessage } from 'naive-ui'
import { errorText, post } from '../api'
const emit = defineEmits<{ imported: [] }>()
const message = useMessage(),
  text = ref(''),
  busy = ref(false),
  secrets = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
async function readFile(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0]
  if (!file) return
  if (file.size > 100000) {
    message.error('配置文件最多 100 KB')
    input.value = ''
    return
  }
  try {
    text.value = await file.text()
  } catch (e) {
    message.error(errorText(e))
  }
  input.value = ''
}
async function apply() {
  busy.value = true
  try {
    const result = await post<{ accounts: number }>('/configuration/import', { text: text.value })
    text.value = ''
    message.success(`已导入 ${result.accounts} 个学习通账号配置`)
    emit('imported')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = false
  }
}
async function download() {
  busy.value = true
  try {
    const response = await fetch(`/api/configuration/export?include_secrets=${secrets.value}`, {
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error('导出失败，请刷新登录状态后重试')
    const url = URL.createObjectURL(await response.blob()),
      link = document.createElement('a')
    link.href = url
    link.download = 'yatori-config.yml'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    message.success('配置已导出')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <section class="panel settings-panel">
    <div class="settings-heading">
      <div>
        <h2>Yatori 配置文件</h2>
        <p>导入原版生成器的 YAML，或导出当前账号和课程配置</p>
      </div>
    </div>
    <NAlert type="info" class="mb-20"
      >按学习通账号匹配更新，新账号会自动添加。导入后请登录验证并同步课程，已有任务保留创建时的配置。</NAlert
    >
    <input ref="fileInput" type="file" accept=".yml,.yaml" hidden @change="readFile" /><NButton
      class="mb-20"
      @click="fileInput?.click()"
      >选择 YAML 文件</NButton
    >
    <NInput
      v-model:value="text"
      type="textarea"
      :rows="8"
      placeholder="也可以在这里粘贴 Yatori config.yml 内容"
      autocomplete="off"
    />
    <div class="settings-actions">
      <NButton type="primary" :disabled="!text.trim()" :loading="busy" @click="apply"
        >导入配置</NButton
      >
    </div>
    <div class="settings-heading mt-16">
      <div>
        <h2>导出配置</h2>
        <p>默认省略密码、API Key 和代理授权</p>
      </div>
    </div>
    <NSpace align="center"
      ><NSwitch v-model:value="secrets" aria-label="导出包含凭据" /><span
        >包含账号密码和服务密钥</span
      ></NSpace
    >
    <NAlert v-if="secrets" type="warning" class="mt-16"
      >下载文件将包含明文凭据，请保存在受信任的位置。</NAlert
    >
    <div class="settings-actions">
      <NButton :loading="busy" @click="download">导出 config.yml</NButton>
    </div>
  </section>
</template>
