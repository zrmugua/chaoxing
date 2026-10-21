import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/accounts',
      component: () => import('./pages/AccountsPage.vue'),
      meta: { title: '学习账号', description: '进入账号，选择课程并管理学习' },
    },
    {
      path: '/accounts/:id',
      component: () => import('./pages/AccountLearningPage.vue'),
      meta: { title: '账号学习', description: '课程选择、学习进度与实时日志' },
    },
    {
      path: '/dashboard',
      component: () => import('./pages/DashboardPage.vue'),
      meta: { title: '首页统计', description: '账号、课程与后台执行统计' },
    },
    {
      path: '/courses',
      component: () => import('./pages/CoursesPage.vue'),
      meta: { title: '课程管理', description: '查看章节、任务点与平台确认状态' },
    },
    {
      path: '/tasks',
      component: () => import('./pages/TasksPage.vue'),
      meta: { title: '任务中心', description: '管理任务队列、执行进度与重试' },
    },
    {
      path: '/runs',
      component: () => import('./pages/RunsPage.vue'),
      meta: { title: '运行记录', description: '查询历次执行的耗时与结果' },
    },
    {
      path: '/logs',
      component: () => import('./pages/LogsPage.vue'),
      meta: { title: '系统日志', description: '筛选和追踪任务运行日志' },
    },
    {
      path: '/settings',
      component: () => import('./pages/SettingsPage.vue'),
      meta: { title: '系统设置', description: '默认学习规则、公共答题服务与任务通知' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
