<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps<{ title: string; description?: string }>()
</script>
<template>
  <div class="empty-state">
    <div class="empty-icon"><Inbox :size="26" :stroke-width="1.5" /></div>
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>
