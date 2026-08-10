<template>
  <div class="page-skeleton">
    <el-skeleton :rows="rows" animated />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ rows?: number }>(), { rows: 6 })
</script>

<style scoped>
.page-skeleton { padding: 8px 0; }
</style>
