import type { TagProps } from 'naive-ui'
import type { Timestamp } from './types'

const labels: Record<string, string> = {
  pending: '排队中',
  queued: '排队中',
  running: '执行中',
  paused: '已暂停',
  pausing: '暂停中',
  stopping: '停止中',
  stopped: '已停止',
  cancelled: '已取消',
  completed: '执行结束',
  succeeded: '执行成功',
  failed: '执行失败',
  retrying: '等待重试',
  interrupted: '执行中断',
  waiting: '等待处理',
  awaiting_user: '待人工处理',
  needs_attention: '待人工处理',
  blocked: '待人工处理',
  waiting_manual: '待人工处理',
  awaiting_confirmation: '待平台确认',
  recovering: '恢复排队中',
  unknown: '待查询',
  unconfirmed: '待确认',
  confirmed: '已确认完成',
  incomplete: '进行中',
  partial: '部分完成',
  not_applicable: '无需确认',
  not_checked: '待查询',
  active: '会话有效',
  valid: '会话有效',
  online: '会话有效',
  logged_in: '会话有效',
  ready: '会话已验证',
  attention: '待处理',
  expired: '会话已过期',
  invalid: '验证失败',
  logged_out: '待登录',
  new: '待登录',
  login: '登录验证',
  sync: '同步课程',
  sync_courses: '同步课程',
  course_sync: '同步章节',
  sync_chapters: '同步章节',
  sync_assessments: '同步作业与考试',
  study: '课程学习',
  study_course: '课程学习',
  account_login: '登录验证',
  account_sync: '同步课程',
}
export function label(value: string) {
  return labels[value] || value || '—'
}
export function serverLabel(state: string, kind: string) {
  if (state === 'pending') return '待确认'
  if (state === 'unknown') return '待查询'
  if (state === 'confirmed') return kind === 'study' ? '已确认完成' : '已核验'
  return label(state)
}
export function statusType(value: string): TagProps['type'] {
  if (
    [
      'completed',
      'succeeded',
      'confirmed',
      'active',
      'valid',
      'online',
      'logged_in',
      'ready',
    ].includes(value)
  )
    return 'success'
  if (['running', 'pending', 'queued', 'retrying', 'recovering'].includes(value)) return 'info'
  if (['failed', 'invalid', 'expired'].includes(value)) return 'error'
  if (
    [
      'paused',
      'pausing',
      'waiting',
      'blocked',
      'awaiting_user',
      'needs_attention',
      'interrupted',
      'partial',
      'waiting_manual',
      'awaiting_confirmation',
      'attention',
    ].includes(value)
  )
    return 'warning'
  return 'default'
}
function timestamp(value: Timestamp) {
  return typeof value === 'number'
    ? value * 1000
    : value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value)
      ? value
      : `${value}Z`
}
export function date(value?: Timestamp | null, compact = false) {
  if (!value) return '—'
  const parsed = new Date(timestamp(value))
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString(
    'zh-CN',
    compact
      ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }
      : {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        },
  )
}
export function duration(start?: Timestamp | null, end?: Timestamp | null) {
  if (!start) return '—'
  const ms =
    (end ? new Date(timestamp(end)).getTime() : Date.now()) - new Date(timestamp(start)).getTime()
  const seconds = Math.max(0, Math.round(ms / 1000))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`
}
export function progress(value: number) {
  return Math.min(100, Math.max(0, value))
}
