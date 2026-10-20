import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { api, errorText } from '../api'

export function useResource<T>(path: string, initial: T, interval = 0) {
  const data = shallowRef<T>(initial)
  const loading = ref(false)
  const error = ref('')
  let timer: ReturnType<typeof setInterval> | undefined
  let alive = true
  let pending = false
  async function refresh() {
    if (pending) return
    pending = true
    loading.value = true
    try {
      const result = await api<T>(path)
      if (alive) {
        data.value = result
        error.value = ''
      }
    } catch (e) {
      if (alive) error.value = errorText(e)
    } finally {
      pending = false
      if (alive) loading.value = false
    }
  }
  onMounted(() => {
    void refresh()
    if (interval)
      timer = setInterval(() => {
        if (!document.hidden) void refresh()
      }, interval)
  })
  onUnmounted(() => {
    alive = false
    if (timer) clearInterval(timer)
  })
  return { data, loading, error, refresh }
}
