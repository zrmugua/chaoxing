<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NTooltip, useMessage } from 'naive-ui'
import { GraduationCap, KeyRound, Moon, ShieldCheck, Sun, UserRound } from 'lucide-vue-next'
import { errorText, post } from '../api'
import type { AuthStatus } from '../types'

const props = defineProps<{ initialized: boolean; dark: boolean }>()
const emit = defineEmits<{ authenticated: [AuthStatus]; toggleTheme: [] }>()
const message = useMessage()
const username = ref('')
const password = ref('')
const setupToken = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  if (busy.value) return
  if (!username.value.trim() || !password.value) {
    message.warning('请填写管理员用户名和密码')
    return
  }
  if (!props.initialized && (password.value.length < 12 || setupToken.value.length < 24)) {
    message.warning('管理员密码至少 12 位，初始化令牌至少 24 位')
    return
  }
  busy.value = true
  error.value = ''
  try {
    emit(
      'authenticated',
      await post<AuthStatus>(props.initialized ? '/auth/login' : '/auth/setup', {
        username: username.value.trim(),
        password: password.value,
        ...(!props.initialized ? { setup_token: setupToken.value } : {}),
      }),
    )
    password.value = ''
    setupToken.value = ''
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-story" aria-label="学习管理工作台">
      <div class="login-story-content">
        <a href="/" class="login-brand">
          <span class="brand-icon"><GraduationCap :size="23" :stroke-width="1.7" /></span>
          <span>学习通<span>学习管理控制台</span></span>
        </a>
        <div class="eyebrow">CHAOXING CONTROL CONSOLE</div>
        <h1>选好课程，<br />掌握学习进度。</h1>
        <p>进入账号即可选择课程并开始学习，<br />实时查看课程活动、平台进度和原始日志。</p>
        <div class="login-story-features">
          <div><strong>统一管理</strong><span>账号与课程集中查看</span></div>
          <div><strong>学习可追踪</strong><span>课程进度与日志随时查看</span></div>
        </div>
      </div>
      <div class="login-story-footer">CHAOXING CONSOLE<span>学习管理工作台</span></div>
    </section>
    <section class="login-form-panel">
      <div class="login-theme-toggle">
        <NTooltip>
          <template #trigger>
            <NButton
              quaternary
              circle
              :aria-label="dark ? '切换浅色模式' : '切换深色模式'"
              @click="emit('toggleTheme')"
              ><Sun v-if="dark" :size="18" /><Moon v-else :size="18"
            /></NButton>
          </template>
          {{ dark ? '浅色模式' : '深色模式' }}
        </NTooltip>
      </div>
      <div class="login-form">
        <div class="login-mobile-brand">
          <span class="brand-icon"><GraduationCap :size="20" :stroke-width="1.7" /></span>
          <strong>学习通控制台</strong>
        </div>
        <div class="eyebrow">{{ initialized ? 'SECURE ACCESS' : 'INITIAL SETUP' }}</div>
        <h2>{{ initialized ? '登录控制台' : '创建管理员账号' }}</h2>
        <p class="login-form-description">
          {{
            initialized
              ? '使用管理员账号访问学习管理工作台。'
              : '完成首次设置，开始管理账号与课程。'
          }}
        </p>
        <NAlert v-if="error" type="error" :show-icon="true" class="mb-20">{{ error }}</NAlert>
        <NForm @submit.prevent="submit">
          <NFormItem label="管理员用户名">
            <NInput
              v-model:value="username"
              placeholder="请输入用户名"
              size="large"
              autocomplete="username"
              :maxlength="64"
              :disabled="busy"
              ><template #prefix><UserRound :size="16" /></template
            ></NInput>
          </NFormItem>
          <NFormItem label="管理员密码">
            <NInput
              v-model:value="password"
              type="password"
              show-password-on="click"
              :placeholder="initialized ? '请输入密码' : '设置至少 12 位密码'"
              size="large"
              :autocomplete="initialized ? 'current-password' : 'new-password'"
              :disabled="busy"
              ><template #prefix><KeyRound :size="16" /></template
            ></NInput>
          </NFormItem>
          <NFormItem v-if="!initialized" label="初始化令牌">
            <NInput
              v-model:value="setupToken"
              type="password"
              show-password-on="click"
              placeholder="部署时设置的 SETUP_TOKEN"
              size="large"
              autocomplete="off"
              :disabled="busy"
              ><template #prefix><ShieldCheck :size="16" /></template
            ></NInput>
          </NFormItem>
          <p v-if="!initialized" class="form-hint">
            初始化令牌来自服务器环境配置，完成设置后使用管理员账号登录。
          </p>
          <NButton type="primary" size="large" block attr-type="submit" :loading="busy">
            {{ initialized ? '进入控制台' : '创建管理员并进入' }}
            <template #icon><ShieldCheck :size="17" /></template>
          </NButton>
        </NForm>
        <div class="login-security">
          <ShieldCheck :size="16" />
          <span>管理员统一管理账号、课程与学习记录。</span>
        </div>
      </div>
      <div class="login-panel-footer">学习通 · 学习管理控制台</div>
    </section>
  </main>
</template>
