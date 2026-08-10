<template>
  <el-alert v-if="message" type="error" :closable="false" show-icon :title="message">
    <template #default>
      <el-button size="small" type="primary" @click="$emit('retry')">重试</el-button>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
defineProps<{ message?: string }>()
defineEmits<{ retry: [] }>()
</script>
