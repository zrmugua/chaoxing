<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  darkTheme,
  dateZhCN,
  NAlert,
  NButton,
  NConfigProvider,
  NDialogProvider,
  NGlobalStyle,
  NMessageProvider,
  NSpin,
  zhCN,
} from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import { api, errorText, setCsrf } from './api'
import type { AuthStatus } from './types'
import ConsoleShell from './components/ConsoleShell.vue'
import LoginPage from './pages/LoginPage.vue'

const auth = ref<AuthStatus | null>(null)
const error = ref('')
const loading = ref(true)
const dark = ref(localStorage.getItem('console-theme') === 'dark')
const theme = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: dark.value ? '#60a5fa' : '#2563eb',
    primaryColorHover: dark.value ? '#93c5fd' : '#3b82f6',
    primaryColorPressed: dark.value ? '#3b82f6' : '#1d4ed8',
    primaryColorSuppl: dark.value ? '#60a5fa' : '#2563eb',
    borderRadius: '6px',
    fontFamily: '"Segoe UI", "Microsoft YaHei", system-ui, sans-serif',
    fontSize: '14px',
    ...(dark.value
      ? {
          bodyColor: '#0f172a',
          cardColor: '#182235',
          modalColor: '#182235',
          popoverColor: '#1e293b',
          textColorBase: '#e2e8f0',
          borderColor: '#293548',
        }
      : {
          bodyColor: '#f8fafc',
          cardColor: '#ffffff',
          modalColor: '#ffffff',
          popoverColor: '#ffffff',
          textColorBase: '#0f172a',
          borderColor: '#e2e8f0',
        }),
  },
  Button: { fontWeight: '500', heightMedium: '36px', heightLarge: '40px' },
  Input: { heightMedium: '36px', heightLarge: '40px' },
  Card: { borderRadius: '10px', paddingMedium: '20px' },
  DataTable: { thColor: dark.value ? '#1e293b' : '#f8fafc', thFontWeight: '500' },
}))
watch(
  dark,
  (value) => {
    localStorage.setItem('console-theme', value ? 'dark' : 'light')
    document.documentElement.dataset.theme = value ? 'dark' : 'light'
  },
  { immediate: true },
)
function authenticated(value: AuthStatus) {
  auth.value = value
  setCsrf(value.csrf)
}
async function loadAuth() {
  loading.value = true
  try {
    authenticated(await api<AuthStatus>('/auth/status'))
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
function expired() {
  if (auth.value?.authenticated) void loadAuth()
}
onMounted(() => {
  void loadAuth()
  window.addEventListener('session-expired', expired)
})
onUnmounted(() => window.removeEventListener('session-expired', expired))
</script>

<template>
  <NConfigProvider
    :theme="dark ? darkTheme : null"
    :theme-overrides="theme"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <NGlobalStyle />
    <NMessageProvider
      ><NDialogProvider>
        <div v-if="loading" class="initial-loading">
          <NSpin size="large" /><span>正在连接控制台</span>
        </div>
        <div v-else-if="error" class="initial-loading">
          <NAlert type="error" title="连接失败">{{ error }}</NAlert
          ><NButton @click="loadAuth">重新连接</NButton>
        </div>
        <ConsoleShell
          v-else-if="auth?.authenticated"
          :username="auth.username || '管理员'"
          :dark="dark"
          @toggle-theme="dark = !dark"
          @logout="loadAuth"
        />
        <LoginPage
          v-else-if="auth"
          :initialized="auth.initialized"
          :dark="dark"
          @authenticated="authenticated"
          @toggle-theme="dark = !dark"
        /> </NDialogProvider
    ></NMessageProvider>
  </NConfigProvider>
</template>
