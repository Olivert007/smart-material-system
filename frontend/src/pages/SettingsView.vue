<template>
  <div class="settings">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="受控内网 · 可信操作主体"
      description="当前阶段适合受控内网部署。浏览器中的角色与令牌仅用于本地体验分流，不能作为真实授权依据；扩大访问范围前须补正式身份与权限设计。"
    />
    <el-form label-width="120px" style="max-width: 520px">
      <el-form-item label="操作令牌">
        <el-input v-model="token" type="password" show-password placeholder="与后端配置的操作令牌一致" />
      </el-form-item>
      <el-form-item label="本地体验角色">
        <el-select v-model="role" style="width: 200px">
          <el-option label="运维" value="ops" />
          <el-option label="治理" value="govern" />
          <el-option label="接入" value="intake" />
          <el-option label="只读" value="viewer" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="save">保存到本机</el-button>
        <el-button @click="clear">清除</el-button>
      </el-form-item>
    </el-form>
    <p class="hint">运维：全部写操作 · 治理：治理确认 · 接入：接入/发布 · 只读：只读。客户端 payload 不得定义 actor 或授权范围。</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const token = ref('')
const role = ref('ops')

onMounted(() => {
  token.value = localStorage.getItem('ops_token') || ''
  role.value = localStorage.getItem('ops_role') || 'ops'
})

function save() {
  localStorage.setItem('ops_token', token.value.trim())
  localStorage.setItem('ops_role', role.value)
  ElMessage.success('已保存到本机浏览器')
}

function clear() {
  localStorage.removeItem('ops_token')
  localStorage.removeItem('ops_role')
  token.value = ''
  role.value = 'ops'
  ElMessage.success('已清除')
}
</script>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 16px; }
.hint { color: #909399; font-size: 13px; margin: 0; }
</style>
