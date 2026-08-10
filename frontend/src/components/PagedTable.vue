<template>
  <div class="paged-table">
    <slot />
    <div v-if="showPager" class="pager">
      <el-pagination
        v-model:current-page="pageModel"
        v-model:page-size="sizeModel"
        :page-sizes="pageSizes"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @size-change="emit('change')"
        @current-change="emit('change')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    page: number
    pageSize: number
    total: number
    pageSizes?: number[]
    showPager?: boolean
  }>(),
  {
    pageSizes: () => [10, 20, 50, 100],
    showPager: true,
  },
)

const emit = defineEmits<{
  'update:page': [number]
  'update:pageSize': [number]
  change: []
}>()

const pageModel = computed({
  get: () => props.page,
  set: (v: number) => emit('update:page', v),
})

const sizeModel = computed({
  get: () => props.pageSize,
  set: (v: number) => emit('update:pageSize', v),
})
</script>

<style scoped>
.paged-table { display: flex; flex-direction: column; gap: 12px; }
.pager { display: flex; justify-content: flex-end; }
</style>
