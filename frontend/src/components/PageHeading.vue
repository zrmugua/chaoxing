<script setup lang="ts">
defineProps<{ title: string; description: string; eyebrow?: string }>()
</script>
<template>
  <div class="page-heading">
    <div>
      <div v-if="eyebrow" class="eyebrow">{{ eyebrow }}</div>
      <h2>{{ title }}</h2>
      <p>{{ description }}</p>
    </div>
    <div class="heading-actions"><slot /></div>
  </div>
</template>
