<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { NButton, NTooltip, useMessage } from 'naive-ui'
import {
  Clock3,
  GraduationCap,
  LogOut,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings2,
  Sun,
  Terminal,
  UsersRound,
} from 'lucide-vue-next'
import { errorText, post } from '../api'
import CompletionTone from './CompletionTone.vue'

defineProps<{ username: string; dark: boolean }>()
const emit = defineEmits<{ toggleTheme: []; logout: [] }>()
const route = useRoute()
const message = useMessage()
const collapsed = ref(localStorage.getItem('console-sidebar') === 'collapsed')
const signingOut = ref(false)
const mobileNav = ref<HTMLElement | null>(null)
const title = computed(() => String(route.meta.title || '仪表盘'))
const description = computed(() => String(route.meta.description || '学习管理工作台'))
const items = [
  { path: '/accounts', title: '学习账号', icon: UsersRound },
  { path: '/settings', title: '学习设置', icon: Settings2 },
  { path: '/runs', title: '运行记录', icon: Clock3 },
  { path: '/logs', title: '系统日志', icon: Terminal },
]
const isActive = (path: string) => route.path === path || route.path.startsWith(`${path}/`)

async function revealActiveMobileItem() {
  await nextTick()
  if (!window.matchMedia('(max-width: 1023px)').matches) return
  const navigation = mobileNav.value
  const activeItem = navigation?.querySelector<HTMLAnchorElement>('.mobile-nav-item.active')
  if (!navigation || !activeItem) return
  const navigationBounds = navigation.getBoundingClientRect()
  const itemBounds = activeItem.getBoundingClientRect()
  if (itemBounds.left < navigationBounds.left || itemBounds.right > navigationBounds.right) {
    activeItem.scrollIntoView({ block: 'nearest', inline: 'center' })
  }
}

onMounted(revealActiveMobileItem)
watch(() => route.path, revealActiveMobileItem)

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('console-sidebar', collapsed.value ? 'collapsed' : 'expanded')
}

async function logout() {
  if (signingOut.value) return
  signingOut.value = true
  try {
    await post('/auth/logout')
    emit('logout')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    signingOut.value = false
  }
}
</script>

<template>
  <CompletionTone />
  <div class="console-shell" :class="{ 'is-collapsed': collapsed }">
    <aside id="main-sidebar" class="sidebar" aria-label="控制台侧栏">
      <RouterLink class="brand" to="/" aria-label="学习通控制台首页">
        <span class="brand-icon"><GraduationCap :size="19" :stroke-width="1.8" /></span>
        <span class="brand-copy">学习通<span class="brand-sub">CHAOXING CONSOLE</span></span>
      </RouterLink>
      <nav class="sidebar-nav" aria-label="主导航">
        <RouterLink
          v-for="item in items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          :aria-current="isActive(item.path) ? 'page' : undefined"
          :aria-label="item.title"
          :title="collapsed ? item.title : undefined"
        >
          <component :is="item.icon" :size="17" :stroke-width="1.7" />
          <span class="nav-item-label">{{ item.title }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-bottom">
        <div class="sidebar-user">
          <span class="avatar" aria-hidden="true">{{ username.slice(0, 1).toUpperCase() }}</span>
          <div class="sidebar-user-details">
            <small>当前管理员</small>
            <strong :title="username">{{ username }}</strong>
          </div>
          <NTooltip>
            <template #trigger>
              <NButton
                quaternary
                circle
                class="sidebar-logout"
                aria-label="退出登录"
                :loading="signingOut"
                @click="logout"
                ><LogOut :size="16"
              /></NButton>
            </template>
            退出登录
          </NTooltip>
        </div>
      </div>
    </aside>
    <div class="main-column">
      <header class="topbar">
        <div class="topbar-heading">
          <NButton
            quaternary
            circle
            class="sidebar-toggle"
            :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
            :aria-expanded="!collapsed"
            aria-controls="main-sidebar"
            @click="toggleSidebar"
          >
            <PanelLeftOpen v-if="collapsed" :size="17" />
            <PanelLeftClose v-else :size="17" />
          </NButton>
          <div class="topbar-title-group">
            <h1 class="topbar-title">{{ title }}</h1>
            <p class="topbar-subtitle">{{ description }}</p>
          </div>
        </div>
        <div class="topbar-actions">
          <NTooltip>
            <template #trigger>
              <NButton
                quaternary
                circle
                :aria-label="dark ? '切换浅色模式' : '切换深色模式'"
                @click="emit('toggleTheme')"
                ><Sun v-if="dark" :size="17" /><Moon v-else :size="17"
              /></NButton>
            </template>
            {{ dark ? '浅色模式' : '深色模式' }}
          </NTooltip>
          <div class="console-status"><span class="status-dot online" />管理员会话</div>
          <NTooltip>
            <template #trigger>
              <NButton
                quaternary
                circle
                class="mobile-logout"
                aria-label="退出登录"
                :loading="signingOut"
                @click="logout"
                ><LogOut :size="17"
              /></NButton>
            </template>
            退出登录
          </NTooltip>
        </div>
      </header>
      <main class="page-content"><RouterView /></main>
      <footer class="main-footer">
        <span>学习通 · 学习管理控制台</span><span>CHAOXING CONSOLE</span>
      </footer>
    </div>
    <nav ref="mobileNav" class="mobile-nav" aria-label="移动端导航">
      <RouterLink
        v-for="item in items"
        :key="item.path"
        :to="item.path"
        class="mobile-nav-item"
        :class="{ active: isActive(item.path) }"
        :aria-current="isActive(item.path) ? 'page' : undefined"
      >
        <component :is="item.icon" :size="18" :stroke-width="1.7" />
        <span>{{ item.title }}</span>
      </RouterLink>
    </nav>
  </div>
</template>
