<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import type { Task } from '../types'
let audio: AudioContext | undefined
let timer: ReturnType<typeof setInterval> | undefined
let previous: Map<number, string> | undefined
let busy = false,
  alive = true
function activate() {
  try {
    audio ||= new AudioContext()
    if (audio.state === 'suspended') void audio.resume().catch(() => {})
  } catch {
    /* Audio availability depends on the client browser. */
  }
}
async function poll() {
  if (busy || document.hidden) return
  busy = true
  try {
    const settings = await api<{ completion_tone: boolean }>('/settings')
    if (!settings.completion_tone) {
      previous = undefined
      return
    }
    const tasks = await api<Task[]>('/tasks')
    if (
      alive &&
      previous &&
      audio?.state === 'running' &&
      tasks.some(
        (t) =>
          t.kind === 'study' &&
          t.state === 'completed' &&
          previous?.has(t.id) &&
          previous.get(t.id) !== 'completed',
      )
    ) {
      const oscillator = audio.createOscillator(),
        gain = audio.createGain()
      oscillator.frequency.value = 660
      gain.gain.value = 0.08
      oscillator.connect(gain)
      gain.connect(audio.destination)
      oscillator.start()
      oscillator.stop(audio.currentTime + 0.18)
    }
    previous = new Map(tasks.map((t) => [t.id, t.state]))
  } catch {
    /* The active page reports API and session errors. */
  } finally {
    busy = false
  }
}
onMounted(() => {
  document.addEventListener('pointerdown', activate, { once: true })
  void poll()
  timer = setInterval(poll, 8000)
})
onUnmounted(() => {
  alive = false
  clearInterval(timer)
  document.removeEventListener('pointerdown', activate)
  void audio?.close()
})
</script>
<template><span hidden aria-hidden="true" /></template>
