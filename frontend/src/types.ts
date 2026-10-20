export interface AuthStatus {
  initialized: boolean
  authenticated: boolean
  csrf: string
  username?: string
}
export type Timestamp = string | number
export interface Account {
  id: number
  label: string
  status: string
  checked_at: Timestamp | null
  created_at: Timestamp
}
export interface Course {
  id: number
  account_id: number
  title: string
  teacher: string
  remote_id: string
  clazz_id: string
  synced_at: Timestamp | null
}
export interface Chapter {
  id: number
  remote_id: string
  title: string
  job_count: number
  confirmed: boolean
  locked: boolean
  synced_at: Timestamp | null
}
export interface Task {
  id: number
  account_id: number
  course_id: number | null
  kind: string
  state: string
  server_state: string
  progress: number
  attempts: number
  max_attempts: number
  message: string
  created_at: Timestamp
  updated_at: Timestamp
  started_at: Timestamp | null
  finished_at: Timestamp | null
}
export interface Run {
  id: number
  task_id: number
  attempt: number
  started_at: Timestamp
  finished_at: Timestamp | null
  state: string
  message: string
}
export interface Log {
  id: number
  task_id: number | null
  level: string
  message: string
  created_at: Timestamp
}
export interface Dashboard {
  accounts: number
  courses: number
  tasks: number
  states: Record<string, number>
  worker_online: boolean
  heartbeat: Timestamp | null
}
export interface Settings {
  concurrency: number
  retry_seconds: number
  max_attempts: number
  log_retention_days: number
  log_level: 'debug' | 'info' | 'warning' | 'error'
  completion_tone: boolean
  color_log: boolean
  log_out_file: boolean
  ai: {
    enabled: boolean
    base_url: string
    model: string
    key_configured: boolean
    api_style: 'chat' | 'responses' | 'metaso'
  }
}
export interface StudySettings {
  answer_mode: 'off' | 'ai' | 'question_bank' | 'chaoxing_ai'
  submit_mode: 'save' | 'submit' | 'complete'
  video_mode: 'off' | 'normal' | 'multi_course' | 'multi_node'
  node_concurrency: number
  media_client: 'desktop' | 'mobile'
  audio: boolean
  document: boolean
  read: boolean
  hyperlink: boolean
  chapter_test: boolean
  work: boolean
  exam: boolean
  shuffle: boolean
  include_courses: string[]
  exclude_courses: string[]
  execution_timeout: number
}
export interface Question {
  id: string
  title: string
  options: string[] | Record<string, string>
  type: string
}
export interface QuestionSet {
  chapter_id: string
  job_id: string
  updated_at: Timestamp
  questions: Question[]
}
