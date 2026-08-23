<template>
  <div class="settings">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="本机设置"
      description="配置本机操作口令后，可确认写入、规整发布与模型管理；未配置时仍可浏览与问数（规则路径）。"
    />
    <el-form label-width="120px" style="max-width: 520px">
      <el-form-item label="本机操作口令">
        <el-input v-model="token" type="password" show-password placeholder="与后端 OPS_TOKEN 一致" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="enableLocalVerify">一键启用本地验证</el-button>
        <el-button @click="save">保存到本机</el-button>
        <el-button @click="clear">清除</el-button>
      </el-form-item>
    </el-form>
    <p class="hint">口令仅保存在本机浏览器，用于写入确认；不会上传到外部服务。</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const LOCAL_DEV_TOKEN = 'dev-ops-token-change-me'
const token = ref('')

onMounted(() => {
  token.value = localStorage.getItem('ops_token') || ''
})

function persist() {
  const trimmed = token.value.trim()
  localStorage.setItem('ops_token', trimmed)
  localStorage.setItem('ops_role', trimmed ? 'ops' : 'viewer')
  window.dispatchEvent(new Event('ops-settings-changed'))
}

function enableLocalVerify() {
  token.value = LOCAL_DEV_TOKEN
  persist()
  ElMessage.success('已启用本地验证，可返回数据规整处理问题')
}

function save() {
  persist()
  ElMessage.success('已保存到本机浏览器')
}

function clear() {
  localStorage.removeItem('ops_token')
  localStorage.removeItem('ops_role')
  token.value = ''
  window.dispatchEvent(new Event('ops-settings-changed'))
  ElMessage.success('已清除本机口令')
}
</script>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 16px; }
.hint { color: #909399; font-size: 13px; margin: 0; }
</style>
