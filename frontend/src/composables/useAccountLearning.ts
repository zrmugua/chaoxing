import { computed, onUnmounted, ref, shallowRef, watch, type Ref } from 'vue'
import { api, ApiError, errorText, post } from '../api'
import type { AccountLearning, LearningAction } from '../types'

const sameIds = (left: number[], right: number[]) =>
  left.length === right.length && left.every((id) => right.includes(id))

export function useAccountLearning(accountId: Ref<number>) {
  const data = shallowRef<AccountLearning | null>(null)
  const selection = ref<number[]>([])
  const savedSelection = ref<number[]>([])
  const selectionRevision = ref(0)
  const loading = ref(true)
  const busy = ref('')
  const error = ref('')
  const conflict = ref(false)
  const settingsPending = ref(false)
  const updatedAt = ref<number | null>(null)
  const dirty = computed(() => !sameIds(selection.value, savedSelection.value))
  let generation = 0
  let alive = true
  let controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  let fetching = false

  function accept(next: AccountLearning, replaceSelection = false) {
    if (data.value && next.revision < data.value.revision) return
    if (replaceSelection || !dirty.value) {
      selection.value = [...next.selected_course_ids]
      savedSelection.value = [...next.selected_course_ids]
      selectionRevision.value = next.revision
    }
    data.value = next
    updatedAt.value = Date.now() / 1000
  }

  async function refresh() {
    if (fetching || !accountId.value || busy.value) return
    const current = generation
    fetching = true
    try {
      const next = await api<AccountLearning>(`/accounts/${accountId.value}/learning`, {
        signal: controller.signal,
      })
      if (!alive || current !== generation || busy.value) return
      accept(next)
      if (!conflict.value) error.value = ''
    } catch (e) {
      if (
        alive &&
        current === generation &&
        !(e instanceof DOMException && e.name === 'AbortError')
      )
        error.value = errorText(e)
    } finally {
      if (alive && current === generation) {
        loading.value = false
        fetching = false
      }
    }
  }

  async function perform(kind: LearningAction | 'save', fingerprint?: string) {
    if (!data.value || busy.value) return false
    const current = generation
    const id = accountId.value
    busy.value = kind
    error.value = ''
    // Cancel a polling response that was issued before this mutation.
    controller.abort()
    controller = new AbortController()
    try {
      let next: AccountLearning
      if (kind === 'save') {
        next = await api<AccountLearning>(`/accounts/${id}/learning`, {
          method: 'PUT',
          body: JSON.stringify({
            course_ids: [...selection.value],
            revision: selectionRevision.value,
            fingerprint,
          }),
          signal: controller.signal,
        })
      } else {
        next = await post<AccountLearning>(`/accounts/${id}/learning/action`, {
          action: kind,
          revision: data.value.revision,
          fingerprint,
        })
      }
      if (!alive || current !== generation) return false
      accept(next, kind === 'save')
      conflict.value = false
      if (kind === 'save' || kind === 'start' || kind === 'resume') settingsPending.value = false
      return true
    } catch (e) {
      if (!alive || current !== generation) return false
      if (e instanceof ApiError && e.status === 409) {
        conflict.value = true
        error.value = errorText(e)
        try {
          const latest = await api<AccountLearning>(`/accounts/${id}/learning`, {
            signal: controller.signal,
          })
          if (!alive || current !== generation) return false
          accept(latest)
          selectionRevision.value = latest.revision
        } catch (refreshError) {
          if (alive && current === generation)
            error.value = `${errorText(e)}。最新状态读取失败：${errorText(refreshError)}`
        }
      } else error.value = errorText(e)
      return false
    } finally {
      if (alive && current === generation) busy.value = ''
    }
  }

  async function synchronize(courseId?: number) {
    if (!data.value || busy.value) return false
    const current = generation
    const id = accountId.value
    busy.value = courseId === undefined ? 'sync_courses' : `sync_course:${courseId}`
    error.value = ''
    controller.abort()
    controller = new AbortController()
    try {
      await post(courseId === undefined ? `/accounts/${id}/sync` : `/courses/${courseId}/sync`)
      if (!alive || current !== generation) return false
      const next = await api<AccountLearning>(`/accounts/${id}/learning`, {
        signal: controller.signal,
      })
      if (!alive || current !== generation) return false
      accept(next)
      return true
    } catch (e) {
      if (alive && current === generation) error.value = errorText(e)
      return false
    } finally {
      if (alive && current === generation) busy.value = ''
    }
  }

  function restore() {
    if (!data.value) return
    selection.value = [...data.value.selected_course_ids]
    savedSelection.value = [...selection.value]
    selectionRevision.value = data.value.revision
    conflict.value = false
    error.value = ''
  }

  async function poll() {
    const current = generation
    if (!document.hidden) await refresh()
    if (alive && current === generation) timer = setTimeout(poll, 2500)
  }

  watch(
    accountId,
    () => {
      generation++
      controller.abort()
      controller = new AbortController()
      if (timer) clearTimeout(timer)
      data.value = null
      selection.value = []
      savedSelection.value = []
      selectionRevision.value = 0
      loading.value = true
      fetching = false
      busy.value = ''
      error.value = ''
      conflict.value = false
      settingsPending.value = false
      updatedAt.value = null
      void poll()
    },
    { immediate: true },
  )

  onUnmounted(() => {
    alive = false
    generation++
    controller.abort()
    if (timer) clearTimeout(timer)
  })

  return {
    data,
    selection,
    dirty,
    loading,
    busy,
    error,
    conflict,
    settingsPending,
    updatedAt,
    refresh,
    perform,
    synchronize,
    restore,
  }
}
