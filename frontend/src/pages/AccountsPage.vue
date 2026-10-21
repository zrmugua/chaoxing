<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
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
import { ArrowRight, Plus, RefreshCw, UsersRound } from 'lucide-vue-next'
import PageHeading from '../components/PageHeading.vue'
import EmptyState from '../components/EmptyState.vue'
import ConfigurationPanel from '../components/ConfigurationPanel.vue'
import { useResource } from '../composables/useResource'
import { api, errorText, post } from '../api'
import { date, label, statusType } from '../format'
import type { Account } from '../types'

const { data, error, loading, refresh } = useResource<Account[]>('/accounts', [], 5000)
const message = useMessage()
const dialog = useDialog()
const router = useRouter()
const show = ref(false)
const editing = ref<Account | null>(null)
const form = ref({ label: '', username: '', password: '' })
const saving = ref(false)
const showConfiguration = ref(false)
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
    else {
      const created = await post<Account>('/accounts', {
        ...form.value,
        label: form.value.label.trim(),
        username: form.value.username.trim(),
      })
      close()
      await router.push(`/accounts/${created.id}`)
      try {
        await post(`/accounts/${created.id}/sync`)
        message.success('账号已添加，正在登录并同步课程列表')
      } catch (e) {
        message.warning(`账号已添加，自动同步暂未启动：${errorText(e)}。可在账号页重新同步。`)
      }
      return
    }
    message.success('账号配置已更新')
    close()
    await refresh()
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
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
  <PageHeading title="学习账号" description="进入账号，选择课程、查看进度并管理学习。"
    ><NButton @click="showConfiguration = true">导入 / 导出配置</NButton
    ><NButton :loading="loading" @click="refresh"
      ><template #icon><RefreshCw :size="15" /></template>刷新</NButton
    ><NButton type="primary" @click="open()"
      ><template #icon><Plus :size="17" /></template>添加账号</NButton
    ></PageHeading
  >
  <NAlert v-if="error" type="error" class="mb-20">{{ error }}</NAlert>
  <section class="panel">
    <div class="panel-heading">
      <h2>
        学习通账号<span class="count-badge">{{ data.length }}</span>
      </h2>
      <span class="muted">课程选择持续保存</span>
    </div>
    <div v-if="data.length" class="learning-account-list" role="list">
      <article
        v-for="account in data"
        :key="account.id"
        class="learning-account-row"
        role="listitem"
      >
        <RouterLink
          :to="`/accounts/${account.id}`"
          class="learning-account-link"
          :aria-label="`进入 ${account.label} 的学习页面`"
        >
          <div class="account-cell">
            <span class="account-avatar"><UsersRound :size="19" /></span>
            <div>
              <div class="cell-title">{{ account.label }}</div>
              <div class="cell-subtitle">最近登录检查 {{ date(account.checked_at, true) }}</div>
            </div>
          </div>
          <div class="account-entry-state">
            <NTag :type="statusType(account.status)" :bordered="false" round size="small">{{
              label(account.status)
            }}</NTag>
            <span class="account-entry-label">进入学习 <ArrowRight :size="16" /></span>
          </div>
        </RouterLink>
        <div class="learning-account-actions">
          <RouterLink
            :to="{ path: `/accounts/${account.id}`, query: { settings: 'learning' } }"
            class="text-link account-settings-link"
            :aria-label="`${account.label} · 账号学习配置`"
            >账号学习配置</RouterLink
          >
          <NButton size="small" quaternary @click="open(account)">编辑</NButton
          ><NButton size="small" quaternary type="error" @click="remove(account)">删除</NButton>
        </div>
      </article>
    </div>
    <EmptyState
      v-else
      title="连接你的第一个学习账号"
      description="添加账号后自动登录并同步课程，勾选课程即可开始学习。"
      ><NButton type="primary" @click="open()">添加学习通账号</NButton></EmptyState
    >
  </section>
  <p class="page-note">
    每个账号独立保存课程选择、学习规则和登录会话。登录或学习过程中需要处理的提示，会显示在账号页和原始日志中。
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
  <NDrawer v-model:show="showConfiguration" :width="'min(760px, 100vw)'"
    ><NDrawerContent title="Yatori 配置文件" closable
      ><ConfigurationPanel @imported="refresh" /></NDrawerContent
  ></NDrawer>
</template>

<style scoped>
.learning-account-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding: 0 18px 0 0;
}
.learning-account-row:last-child {
  border-bottom: 0;
}
.learning-account-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 24px;
  min-width: 0;
  flex: 1;
}
.learning-account-link:hover {
  background: var(--hover);
}
.account-cell {
  min-width: 0;
}
.account-cell > div {
  min-width: 0;
}
.cell-title {
  font-size: 15px;
  overflow-wrap: anywhere;
}
.account-entry-state {
  display: flex;
  align-items: center;
  gap: 26px;
  flex-shrink: 0;
}
.account-entry-label {
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.learning-account-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.account-settings-link {
  padding: 8px;
  white-space: nowrap;
}
@media (max-width: 650px) {
  .learning-account-row {
    align-items: stretch;
    flex-wrap: wrap;
    padding: 0;
  }
  .learning-account-link {
    width: 100%;
    flex: auto;
    flex-wrap: wrap;
    padding: 20px 16px 12px;
    gap: 16px;
  }
  .account-entry-state {
    width: 100%;
    padding-left: 46px;
    justify-content: space-between;
    gap: 12px;
  }
  .learning-account-actions {
    padding: 0 12px 10px;
    margin-left: auto;
  }
}
</style>
