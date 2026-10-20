<script setup lang="ts">
import { ref } from 'vue'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NDrawer,
  NDrawerContent,
  NSpace,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { Plus, RefreshCw, ShieldCheck, UsersRound } from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import EmptyState from '../components/EmptyState.vue'
import LearningRulesPanel from '../components/LearningRulesPanel.vue'
import RunConfirmation from '../components/RunConfirmation.vue'
import ConfigurationPanel from '../components/ConfigurationPanel.vue'
import { useResource } from '../composables/useResource'
import { api, errorText, post } from '../api'
import { date, label, statusType } from '../format'
import type { Account } from '../types'

const { data, error, loading, refresh } = useResource<Account[]>('/accounts', [], 5000)
const message = useMessage()
const dialog = useDialog()
const show = ref(false)
const editing = ref<Account | null>(null)
const form = ref({ label: '', username: '', password: '' })
const saving = ref(false)
const busy = ref<number | null>(null)
const rulesAccount = ref<Account | null>(null)
const showRules = ref(false)
const showRun = ref(false)
const showConfiguration = ref(false)
function prepareRun() {
  showRules.value = false
  showRun.value = true
}
function openRules(account: Account) {
  rulesAccount.value = account
  showRules.value = true
}
function open(account?: Account) {
  editing.value = account || null
  form.value = { label: account?.label || '', username: '', password: '' }
  show.value = true
}
function close() {
  show.value = false
  form.value.password = ''
  form.value.username = ''
}
async function save() {
  if (
    !form.value.label.trim() ||
    (!editing.value && (!form.value.username.trim() || !form.value.password))
  ) {
    message.warning('请填写账号名称、学习通账号和密码')
    return
  }
  saving.value = true
  try {
    if (editing.value)
      await api(`/accounts/${editing.value.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          label: form.value.label.trim(),
          ...(form.value.password ? { password: form.value.password } : {}),
        }),
      })
    else
      await post('/accounts', {
        ...form.value,
        label: form.value.label.trim(),
        username: form.value.username.trim(),
      })
    message.success(editing.value ? '账号配置已更新' : '账号已添加，请进行登录验证')
    close()
    await refresh()
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function execute(account: Account, action: string) {
  busy.value = account.id
  try {
    await post(`/accounts/${account.id}/${action}`)
    message.success(action === 'login' ? '登录验证任务已加入队列' : '课程同步任务已加入队列')
    await refresh()
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = null
  }
}
function remove(account: Account) {
  dialog.warning({
    title: `删除「${account.label}」`,
    content: '删除账号会移除关联的课程及任务记录。请先停止该账号正在执行的任务。',
    positiveText: '确认删除',
    negativeText: '保留账号',
    onPositiveClick: async () => {
      try {
        await api(`/accounts/${account.id}`, { method: 'DELETE' })
        message.success('账号已删除')
        await refresh()
      } catch (e) {
        message.error(errorText(e))
      }
    },
  })
}
</script>

<template>
  <PageHeading title="学习通账号" description="添加账号、验证登录并同步课程。"
    ><NButton @click="showConfiguration = true">导入 / 导出配置</NButton
    ><NButton :loading="loading" @click="refresh"
      ><template #icon><RefreshCw :size="15" /></template>刷新</NButton
    ><NButton type="primary" @click="open()"
      ><template #icon><Plus :size="17" /></template>添加账号</NButton
    ></PageHeading
  >
  <NAlert v-if="error" type="error" class="mb-20">{{ error }}</NAlert>
  <div class="info-strip">
    <ShieldCheck :size="18" /><span
      >每个账号的登录会话、Cookie 和任务状态独立管理，敏感凭据加密存储。</span
    >
  </div>
  <section class="panel">
    <div class="panel-heading">
      <h2>
        学习通账号<span class="count-badge">{{ data.length }}</span>
      </h2>
      <span class="muted">登录后同步课程</span>
    </div>
    <div v-if="data.length" class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>账号</th>
            <th>会话状态</th>
            <th>最近检查</th>
            <th>添加时间</th>
            <th class="actions-cell">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="account in data" :key="account.id">
            <td>
              <div class="account-cell">
                <span class="account-avatar"><UsersRound :size="19" /></span>
                <div>
                  <div class="cell-title">{{ account.label }}</div>
                  <div class="cell-subtitle">账号 #{{ account.id }}</div>
                </div>
              </div>
            </td>
            <td>
              <NTag :type="statusType(account.status)" :bordered="false" round size="small">{{
                label(account.status)
              }}</NTag>
            </td>
            <td class="cell-date">{{ date(account.checked_at, true) }}</td>
            <td class="cell-date">{{ date(account.created_at, true) }}</td>
            <td class="actions-cell">
              <div class="row-actions">
                <NButton
                  size="tiny"
                  secondary
                  type="primary"
                  :loading="busy === account.id"
                  @click="execute(account, 'login')"
                  >登录验证</NButton
                ><NButton
                  size="tiny"
                  secondary
                  :disabled="busy === account.id"
                  @click="execute(account, 'sync')"
                  >同步课程</NButton
                ><NButton size="tiny" quaternary @click="openRules(account)">配置与启动</NButton
                ><RouterLink
                  :to="{ path: '/logs', query: { account_id: account.id } }"
                  class="text-link small"
                  >日志</RouterLink
                ><NButton size="tiny" quaternary @click="open(account)">编辑</NButton
                ><NButton size="tiny" quaternary type="error" @click="remove(account)"
                  >删除</NButton
                >
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState
      v-else
      title="连接你的第一个学习账号"
      description="添加学习通账号后，完成登录验证，即可同步和管理课程。"
      ><NButton type="primary" @click="open()">添加学习通账号</NButton></EmptyState
    >
  </section>
  <p class="page-note">
    登录验证在后台执行。遇到验证码或平台人工确认时，具体提示会记录在任务中心与系统日志中。
  </p>
  <NModal
    :show="show"
    preset="card"
    :title="editing ? '编辑账号' : '添加学习通账号'"
    class="form-modal"
    :mask-closable="!saving"
    @update:show="
      (value) => {
        if (!value) close()
      }
    "
    ><NForm @submit.prevent="save"
      ><NFormItem label="账号名称"
        ><NInput
          v-model:value="form.label"
          placeholder="例如：我的学习账号"
          :maxlength="80" /></NFormItem
      ><NFormItem v-if="!editing" label="学习通账号"
        ><NInput
          v-model:value="form.username"
          placeholder="手机号或学号"
          autocomplete="off" /></NFormItem
      ><NFormItem :label="editing ? '更新密码（选填）' : '学习通密码'"
        ><NInput
          v-model:value="form.password"
          type="password"
          show-password-on="click"
          :placeholder="editing ? '输入新密码后保存' : '输入学习通账号密码'"
          autocomplete="new-password"
      /></NFormItem>
      <p class="form-hint">账号凭据用于与学习通建立独立会话。请仅添加你有权使用的账号。</p>
      <NSpace justify="end"
        ><NButton :disabled="saving" @click="close">取消</NButton
        ><NButton type="primary" attr-type="submit" :loading="saving">{{
          editing ? '保存配置' : '添加账号'
        }}</NButton></NSpace
      ></NForm
    ></NModal
  >
  <NDrawer v-model:show="showRules" :width="'min(680px, 100vw)'"
    ><NDrawerContent :title="`${rulesAccount?.label || ''} · 课程配置`" closable
      ><LearningRulesPanel
        v-if="rulesAccount"
        :key="rulesAccount.id"
        :account-id="rulesAccount.id"
        @start="prepareRun" /></NDrawerContent
  ></NDrawer>
  <RunConfirmation v-model:show="showRun" :account-id="rulesAccount?.id || null" />
  <NDrawer v-model:show="showConfiguration" :width="'min(760px, 100vw)'"
    ><NDrawerContent title="Yatori 配置文件" closable
      ><ConfigurationPanel @imported="refresh" /></NDrawerContent
  ></NDrawer>
</template>
