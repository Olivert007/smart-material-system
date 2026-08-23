<template>
  <div class="govern">
    <el-tabs v-if="!hideOuterTabs" v-model="tab" @tab-change="onTab">
      <el-tab-pane label="待确认字段" name="map" />
      <el-tab-pane label="待确认规则" name="rulelearn" />
      <el-tab-pane label="待匹配物资" name="master" />
      <el-tab-pane label="待解析流水" name="flow" />
      <el-tab-pane label="对账差异" name="reconcile" />
    </el-tabs>

    <p v-if="tabHint && !hideOuterTabs" class="outer-hint">{{ tabHint }}</p>

    <template v-if="tab === 'rulelearn'">
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>待确认规则</span>
            <el-space>
              <el-button v-if="!opsTokenReady" type="primary" @click="goLocalSettings">去本地设置</el-button>
              <el-button v-else type="primary" @click="openCreateRule">新建规则</el-button>
              <el-button :loading="rlBusy" :disabled="!opsTokenReady" @click="runRuleLearn">从历史问题整理</el-button>
              <el-button link type="primary" @click="loadRuleLearn">刷新</el-button>
            </el-space>
          </div>
        </template>
        <el-table :data="rlPendingItems" v-loading="rlLoading" border size="small" empty-text="暂无待确认规则">
          <el-table-column label="规则内容" min-width="280">
            <template #default="{ row }">{{ proposalLabel(row.proposal) }}</template>
          </el-table-column>
          <el-table-column label="影响数据" width="120">
            <template #default="{ row }">影响 {{ row.proposal?.count ?? 0 }} 行</template>
          </el-table-column>
          <el-table-column label="建议" min-width="180">
            <template #default="{ row }">{{ proposalHint(row.proposal) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!opsTokenReady" link type="primary" @click="goLocalSettings">去本地设置</el-button>
              <template v-else>
                <el-button link type="primary" @click="acceptRl(row)">采用</el-button>
                <el-button link type="danger" @click="rejectRl(row.id)">不采用</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
      <el-dialog v-model="createRuleVisible" title="新建规则" width="520px" destroy-on-close>
        <el-form label-width="110px">
          <el-form-item label="规则类型">
            <el-select v-model="createRule.rule_type" style="width: 240px">
              <el-option label="字段叫法规则" value="field_alias" />
              <el-option label="数据校验规则" value="value_check" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="createRule.rule_type === 'field_alias'" label="原始表头">
            <el-input v-model="createRule.header" placeholder="例如：物料描述" />
          </el-form-item>
          <el-form-item label="标准字段">
            <el-select v-model="createRule.std_field" filterable allow-create style="width: 240px">
              <el-option v-for="f in stdFields" :key="f" :label="stdFieldLabel(f)" :value="f" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="createRule.rule_type === 'value_check'" label="校验方式">
            <el-select v-model="createRule.check_type" style="width: 240px">
              <el-option label="必须为正数" value="numeric_positive" />
              <el-option label="不能为空" value="required" />
            </el-select>
          </el-form-item>
          <el-form-item label="影响范围说明">
            <el-input v-model="createRule.scope_note" type="textarea" :rows="2" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createRuleVisible = false">取消</el-button>
          <el-button type="primary" :loading="createRuleBusy" @click="submitCreateRule">写入候选</el-button>
        </template>
      </el-dialog>
    </template>

    <!-- —— 表头映射 —— -->
    <template v-else-if="tab === 'map'">
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>待确认字段</span>
            <el-space>
              <el-button v-if="!opsTokenReady" type="primary" @click="goLocalSettings">去本地设置</el-button>
              <el-button link type="primary" @click="loadMapPending">刷新</el-button>
            </el-space>
          </div>
        </template>
        <PagedTable
          v-model:page="mapPage"
          v-model:page-size="mapPageSize"
          :total="mapPendingTotal"
          @change="loadMapPending"
        >
        <el-table :data="mapPending" v-loading="mapPendingLoading" border size="small" empty-text="暂无待确认">
          <el-table-column label="表头" min-width="120">
            <template #default="{ row }">{{ headerLabel(row.header) }}</template>
          </el-table-column>
          <el-table-column label="原因" width="160">
            <template #default="{ row }">{{ reasonLabel(row.reason) }}</template>
          </el-table-column>
          <el-table-column label="建议" width="120">
            <template #default="{ row }">{{ stdFieldLabel(row.suggested_field) }}</template>
          </el-table-column>
          <el-table-column v-if="mapShowSourceCols" label="工作表" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span :title="fileLabel(row) !== '—' ? `来源文件：${fileLabel(row)}` : undefined">
                {{ sheetLabel(row.sheet) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="处理方式" min-width="180">
            <template #default="{ row }">
              <el-select v-model="row.suggested_field" filterable allow-create size="small" style="width: 160px">
                <el-option label="忽略该表头" value="ignore" />
                <el-option
                  v-if="extraSelectField(row.suggested_field)"
                  :label="stdFieldLabel(row.suggested_field)"
                  :value="row.suggested_field"
                />
                <el-option v-for="f in stdFields" :key="f" :label="stdFieldLabel(f)" :value="f" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!opsTokenReady" link type="primary" @click="goLocalSettings">去本地设置</el-button>
              <el-button v-else link type="primary" @click="confirmMapRow(row)">确认处理</el-button>
            </template>
          </el-table-column>
        </el-table>
        </PagedTable>
      </el-card>

    </template>

    <!-- —— 主数据待审 —— -->
    <template v-else-if="tab === 'master'">
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>待匹配物资</span>
            <el-space>
              <el-button v-if="!opsTokenReady" type="primary" @click="goLocalSettings">去本地设置</el-button>
              <el-button type="primary" :loading="masterProposeBusy" :disabled="!opsTokenReady" @click="runMasterPropose">
                扫描入队
              </el-button>
              <el-button link type="primary" @click="loadMasterPending">刷新</el-button>
            </el-space>
          </div>
        </template>
        <PagedTable
          v-model:page="masterPage"
          v-model:page-size="masterPageSize"
          :total="masterPendingTotal"
          @change="loadMasterPending"
        >
        <el-table :data="masterPending" v-loading="masterPendingLoading" border size="small" empty-text="暂无待审">
          <el-table-column prop="material_code" label="物资编码" width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.material_code || '未维护' }}</template>
          </el-table-column>
          <el-table-column prop="material_name" label="物资名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="spec" label="规格型号" width="120" show-overflow-tooltip />
          <el-table-column label="识别方式" width="140">
            <template #default="{ row }">{{ parseLevelLabel(row.match_level) }}</template>
          </el-table-column>
          <el-table-column label="冲突" width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ conflictLabel(row.conflict_type) }}</template>
          </el-table-column>
          <el-table-column label="候选" min-width="200">
            <template #default="{ row }">
              <span v-if="!(row.candidates || []).length" class="hint">暂无可合并目标</span>
              <el-space v-else wrap>
                <el-tag
                  v-for="c in (row.candidates || []).slice(0, 3)"
                  :key="String(c.material_id) + String(c.why)"
                  size="small"
                  class="cand"
                  :type="row._mergeTo === c.material_id ? 'primary' : 'info'"
                  @click="row._mergeTo = c.material_id"
                >
                  {{ candidateLabel(c) }}
                </el-tag>
              </el-space>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!opsTokenReady" link type="primary" @click="goLocalSettings">去本地设置</el-button>
              <template v-else>
                <el-button link type="success" @click="decideMaster(row, 'approve')">批准</el-button>
                <el-button link type="primary" @click="openAmendMaster(row)">修正</el-button>
                <el-button link type="warning" @click="decideMaster(row, 'merge')">合并</el-button>
                <el-button link type="info" @click="decideMaster(row, 'reject')">拒绝</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
        </PagedTable>
      </el-card>
      <el-dialog v-model="amendMasterVisible" title="修正物资" width="520px" destroy-on-close>
        <el-form label-width="110px">
          <el-form-item label="物资编码">
            <el-input v-model="amendMaster.material_code" />
          </el-form-item>
          <el-form-item label="物资名称">
            <el-input v-model="amendMaster.material_name" />
          </el-form-item>
          <el-form-item label="规格型号">
            <el-input v-model="amendMaster.spec" />
          </el-form-item>
          <el-form-item label="单位">
            <el-input v-model="amendMaster.unit" />
          </el-form-item>
          <el-form-item label="物资种类">
            <el-input v-model="amendMaster.category" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="amendMasterVisible = false">取消</el-button>
          <el-button type="primary" :loading="amendMasterBusy" @click="submitAmendMaster">保存并批准</el-button>
        </template>
      </el-dialog>
    </template>

    <!-- —— 流水解析 —— -->
    <template v-else-if="tab === 'flow'">
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>质量快照</span>
            <el-button link type="primary" @click="loadFlowStats">刷新</el-button>
          </div>
        </template>
        <el-space wrap>
          <el-tag>已发布 {{ flowStats.published_total ?? '—' }}</el-tag>
          <el-tag>规则直接识别 {{ flowStats.published_by_level?.L1 ?? 0 }}</el-tag>
          <el-tag type="warning">规则校验后识别 {{ flowStats.published_by_level?.L2 ?? 0 }}</el-tag>
          <el-tag type="danger">需要人工确认 {{ flowStats.published_by_level?.L3 ?? 0 }}</el-tag>
          <el-tag type="info">待确认 {{ flowStats.pending ?? '—' }}</el-tag>
          <el-tag
            v-for="(n, lvl) in flowStats.pending_by_level || {}"
            :key="'p'+lvl"
            size="small"
            type="warning"
          >
            待确认 {{ parseLevelLabel(String(lvl)) }}: {{ n }}
          </el-tag>
        </el-space>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>待确认列表</span>
            <el-space wrap>
              <el-select v-model="flowStatus" style="width: 120px" @change="onFlowFilter">
                <el-option label="待确认" value="pending" />
                <el-option label="冲突" value="conflict" />
                <el-option label="已确认" value="confirmed" />
                <el-option label="已忽略" value="ignored" />
              </el-select>
              <el-select
                v-model="flowLevelFilter"
                clearable
                placeholder="识别方式"
                style="width: 100px"
                @change="onFlowFilter"
              >
                <el-option label="规则直接识别" value="L1" />
                <el-option label="规则校验后识别" value="L2" />
                <el-option label="需要人工确认" value="L3" />
              </el-select>
              <el-input-number v-model="flowSuggestLimit" :min="1" :max="50" size="small" />
              <el-button :loading="flowLoading" @click="loadFlowPending">刷新</el-button>
              <el-button
                type="warning"
                plain
                :loading="flowDrainBusy"
                :disabled="flowStatus !== 'pending'"
                @click="runFlowSuggestQueue"
              >
                队列批处理（智能建议）
              </el-button>
              <el-button
                type="primary"
                plain
                :loading="flowSuggestBusy"
                :disabled="!selectedPending.length"
                @click="runFlowSuggestSelected"
              >
                生成智能建议
              </el-button>
              <el-button
                type="success"
                :disabled="!selectedPending.length || (flowStatus !== 'pending' && flowStatus !== 'conflict')"
                :loading="flowBatchBusy"
                @click="batchAccept"
              >
                {{ flowStatus === 'conflict' ? '批量覆盖接受' : '批量接受' }}
              </el-button>
              <el-button
                type="danger"
                plain
                :disabled="!selectedPending.length || (flowStatus !== 'pending' && flowStatus !== 'conflict')"
                :loading="flowBatchBusy"
                @click="batchIgnore"
              >
                批量忽略
              </el-button>
            </el-space>
          </div>
        </template>

        <PagedTable
          v-model:page="flowPage"
          v-model:page-size="flowPageSize"
          :total="flowTotal"
          @change="loadFlowPending"
        >
        <el-table
          :data="flowItems"
          v-loading="flowLoading"
          border
          size="small"
          style="width: 100%"
          @selection-change="onFlowSelect"
        >
          <el-table-column
            type="selection"
            width="42"
            :selectable="() => flowStatus === 'pending' || flowStatus === 'conflict'"
          />
          <el-table-column label="识别方式" width="140">
            <template #default="{ row }">{{ parseLevelLabel(row.parse_level) }}</template>
          </el-table-column>
          <el-table-column label="方向" width="70">
            <template #default="{ row }">{{ flowTypeLabel(row.flow_type) }}</template>
          </el-table-column>
          <el-table-column prop="source_sheet" label="工作表" width="120" show-overflow-tooltip />
          <el-table-column prop="text_raw" label="原文" min-width="220" show-overflow-tooltip />
          <el-table-column label="建议摘要" min-width="200">
            <template #default="{ row }">
              <span class="mono">{{ summarizeSuggest(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="建议状态" width="90">
            <template #default="{ row }">{{ modelStateLabel(row.llm_state) }}</template>
          </el-table-column>
          <el-table-column label="角色" width="70">
            <template #default="{ row }">{{ llmRoleLabel(row.llm_role) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button
                link
                type="success"
                :disabled="row.status !== 'pending' && row.status !== 'conflict'"
                @click="decideOne(row, 'accept', row.status === 'conflict')"
              >
                {{ row.status === 'conflict' ? '覆盖接受' : '接受' }}
              </el-button>
              <el-button
                link
                type="primary"
                :disabled="row.status !== 'pending' && row.status !== 'conflict'"
                @click="openAmend(row)"
              >
                修正
              </el-button>
              <el-button
                link
                type="danger"
                :disabled="row.status !== 'pending' && row.status !== 'conflict'"
                @click="decideOne(row, 'ignore')"
              >
                忽略
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        </PagedTable>
      </el-card>

      <el-dialog v-model="amendVisible" title="修正流水建议" width="560px" destroy-on-close>
        <el-form label-width="88px">
          <el-form-item label="原文">
            <div class="hint">{{ amendRow?.text_raw }}</div>
          </el-form-item>
          <el-form-item label="方向">
            <el-select v-model="amendForm.flow_type" style="width: 140px">
              <el-option label="入库" value="IN" />
              <el-option label="出库" value="OUT" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-input v-model="amendForm.flow_date" placeholder="YYYY-MM-DD 或空" />
          </el-form-item>
          <el-form-item label="数量">
            <el-input v-model="amendForm.quantity" placeholder="数字或空" />
          </el-form-item>
          <el-form-item label="单位">
            <el-input v-model="amendForm.unit" />
          </el-form-item>
          <el-form-item label="经手人">
            <el-input v-model="amendForm.person" />
          </el-form-item>
          <el-form-item label="用途">
            <el-input v-model="amendForm.purpose" />
          </el-form-item>
          <el-form-item label="识别方式">
            <el-select v-model="amendForm.parse_level" style="width: 180px">
              <el-option label="规则直接识别" value="L1" />
              <el-option label="规则校验后识别" value="L2" />
              <el-option label="需要人工确认" value="L3" />
            </el-select>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="amendNote" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="amendVisible = false">取消</el-button>
          <el-button type="primary" :loading="flowBatchBusy" @click="submitAmend">提交修正</el-button>
        </template>
      </el-dialog>
    </template>

    <!-- —— 库存对账 —— -->
    <template v-else>
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>差异清单 · 共 {{ reconcileTotal }} 行</span>
            <el-space>
              <el-button :loading="reconcileLoading" @click="loadReconcile">刷新</el-button>
              <el-button :loading="openingSeedBusy" @click="seedOpening">补期初库存</el-button>
              <el-button type="primary" :loading="reconcilePersistBusy" @click="persistReconcile">
                保存结果
              </el-button>
              <el-button :disabled="!reconcileItems.length" @click="exportReconcile">
                导出当前结果
              </el-button>
            </el-space>
          </div>
        </template>
        <el-row :gutter="12" style="margin-bottom: 12px">
          <el-col v-for="c in reconcileCards" :key="c.key" :span="6">
            <el-card shadow="never" body-style="padding: 12px">
              <div class="stat-label">{{ c.label }}</div>
              <div class="stat-value">{{ c.value }}</div>
            </el-card>
          </el-col>
        </el-row>
        <el-table
          :data="reconcileItems"
          v-loading="reconcileLoading"
          border
          size="small"
          max-height="520"
          :row-class-name="gapRowClass"
        >
          <el-table-column label="类别" width="120">
            <template #default="{ row }">
              <el-tooltip :content="gapClassHint(String(row.gap_class))" placement="top">
                <span>{{ gapClassLabel(String(row.gap_class)) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="物资" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.material_name || row.material_code || '未维护' }}</template>
          </el-table-column>
          <el-table-column prop="stock_qty" label="库存" width="90" />
          <el-table-column prop="opening_qty" label="期初" width="90" />
          <el-table-column prop="expected_net" label="库存−期初" width="110" />
          <el-table-column prop="flow_net" label="流水净额" width="110" />
          <el-table-column prop="gap" label="差异" width="100" />
          <el-table-column prop="source_file" label="来源" min-width="160" show-overflow-tooltip />
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>版本与血缘（高级）</span>
            <el-space>
              <el-button :loading="lineageLoading" @click="loadLineageReleases">刷新发布版本</el-button>
            </el-space>
          </div>
        </template>
        <p class="danger-hint">以下操作会修改已发布数据或版本链，执行前请确认 release_id 与影响范围。</p>
        <el-table :data="lineageItems" v-loading="lineageLoading" border size="small" empty-text="暂无发布版本">
          <el-table-column prop="release_id" label="release_id" min-width="200" show-overflow-tooltip />
          <el-table-column prop="target_domain" label="域" width="100" />
          <el-table-column prop="clean_rows" label="行数" width="80" />
          <el-table-column prop="released_at" label="发布时间" width="170" />
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="lineageRebuildId = String(row.release_id)">
                选用
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-form label-width="120px" class="danger-form">
          <el-form-item label="版本取代">
            <el-space wrap>
              <el-input v-model="supersedeNewer" placeholder="较新版本 release_id" style="width: 220px" />
              <span>取代</span>
              <el-input v-model="supersedeOlder" placeholder="较旧版本 release_id" style="width: 220px" />
              <el-button type="danger" plain :loading="lineageActionBusy" @click="runReleaseSupersede">
                执行取代
              </el-button>
            </el-space>
          </el-form-item>
          <el-form-item label="血缘重建">
            <el-space wrap>
              <el-input v-model="lineageRebuildId" placeholder="release_id" style="width: 280px" />
              <el-checkbox v-model="lineageRevokeOnly">仅撤销（不重建）</el-checkbox>
              <el-button type="danger" :loading="lineageActionBusy" @click="runLineageRebuild">
                执行重建
              </el-button>
            </el-space>
          </el-form-item>
        </el-form>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElLink, ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { useRouter } from 'vue-router'
import PagedTable from '@/components/PagedTable.vue'
import { fieldZh as fieldzh } from '@/utils/fields'
import { gateLabel } from '@/utils/gateLabels'
import {
  confirmFlowPending,
  flowOpeningSeed,
  flowReconcile,
  flowReconcilePersist,
  flowStats as fetchFlowStats,
  formatApiError,
  listFlowPending,
  listStdFields,
  listMapPending,
  confirmMapPending,
  suggestFlowPending,
  proposeMasterPending,
  listMasterPending,
  confirmMasterPending,
  proposeRuleLearn,
  listRuleLearnCandidates,
  confirmRuleLearn,
  createRuleLearnCandidate,
  lineageRebuild,
  listLineageReleases,
  releaseSupersede,
  type FlowPendingItem,
  type FlowReconcileItem,
  type MapPendingItem,
  type MasterPendingItem,
} from '@/api/client'
import { parseLevelLabel } from '@/utils/parseLevel'
import { dangerousConfirmMessage } from '@/utils/dangerousConfirm'

const router = useRouter()

/** 治理确认成功后提示，并带"去台账浏览验证"快捷链接（ledger-browse LB-3.3）。 */
function notifyBrowse(title: string, _table?: string) {
  ElNotification({
    title,
    message: h(
      ElLink,
      { type: 'primary', underline: false, onClick: () => router.push('/data?tab=materials') },
      () => '去数据成果查看',
    ),
    type: 'success',
    duration: 4500,
  })
}

const props = withDefaults(
  defineProps<{ initialTab?: string; hideOuterTabs?: boolean }>(),
  { initialTab: 'map', hideOuterTabs: true },
)

const emit = defineEmits<{
  (e: 'tab-change', tab: string): void
  (e: 'queue-changed'): void
}>()

function notifyQueueChanged() {
  emit('queue-changed')
}

const tab = ref(props.initialTab || 'map')

const TOKEN_HINT = '请先到本地设置点击「一键启用本地验证」'

/** 操作令牌是否就绪（响应式：页面 focus / storage 变化时刷新）。 */
const opsTokenReady = ref(Boolean(localStorage.getItem('ops_token')))
function refreshTokenState() {
  opsTokenReady.value = Boolean(localStorage.getItem('ops_token'))
}
window.addEventListener('focus', refreshTokenState)
window.addEventListener('storage', refreshTokenState)
window.addEventListener('ops-settings-changed', refreshTokenState)

function goLocalSettings() {
  router.push({ path: '/system', query: { tab: 'settings' } })
}

function requireOpsToken() {
  if (opsTokenReady.value) return true
  ElMessage.warning(TOKEN_HINT)
  return false
}

const tabHint = computed(() => {
  const map: Record<string, string> = {
    map: '确认系统不确定的字段。',
    rulelearn: '采用后变成后续可复用规则。',
    master: '批准、修正、合并或拒绝候选物资。',
    flow: '审核无法自动确认的出入库记录。',
    reconcile: '查看库存与流水差异，必要时补期初库存或保存结果。',
  }
  return map[tab.value] || ''
})

const stdFields = ref<string[]>(['ignore'])
const rlItems = ref<
  Array<{ id: number; decision: string; proposal?: Record<string, unknown> }>
>([])
const rlLoading = ref(false)
const rlBusy = ref(false)
const createRuleVisible = ref(false)
const createRuleBusy = ref(false)
const createRule = reactive({
  rule_type: 'field_alias' as 'field_alias' | 'value_check',
  header: '',
  std_field: '',
  check_type: 'numeric_positive',
  scope_note: '',
})
const rlPendingItems = computed(() => rlItems.value.filter((x) => x.decision === 'proposed'))
const mapShowSourceCols = computed(() =>
  mapPending.value.some((r) => Boolean(r.sheet) || Boolean(r.file_id)),
)
const mapPending = ref<MapPendingItem[]>([])
const mapPendingTotal = ref(0)
const mapPendingLoading = ref(false)
const mapPage = ref(1)
const mapPageSize = ref(20)

const masterPending = ref<Array<MasterPendingItem & { _mergeTo?: string }>>([])
const masterPendingTotal = ref(0)
const masterPendingLoading = ref(false)
const masterPage = ref(1)
const masterPageSize = ref(20)
const masterProposeBusy = ref(false)
const amendMasterVisible = ref(false)
const amendMasterBusy = ref(false)
const amendMasterRow = ref<(MasterPendingItem & { _mergeTo?: string }) | null>(null)
const amendMaster = reactive({
  material_code: '',
  material_name: '',
  spec: '',
  unit: '',
  category: '',
})

const flowStatus = ref('pending')
const flowLevelFilter = ref<string | undefined>()
const flowPage = ref(1)
const flowPageSize = ref(20)
const flowSuggestLimit = ref(10)
const flowItems = ref<FlowPendingItem[]>([])
const flowTotal = ref(0)
const flowLoading = ref(false)
const flowSuggestBusy = ref(false)
const flowDrainBusy = ref(false)
const flowBatchBusy = ref(false)
const selectedPending = ref<FlowPendingItem[]>([])
const flowStats = reactive<{
  published_total?: number
  published_by_level?: Record<string, number>
  pending_by_level?: Record<string, number>
  l1_ratio?: number | null
  pending?: number
}>({})
const amendVisible = ref(false)
const amendRow = ref<FlowPendingItem | null>(null)
const amendNote = ref('')
const amendForm = reactive({
  flow_type: 'OUT',
  flow_date: '',
  quantity: '',
  unit: '',
  person: '',
  purpose: '',
  parse_level: 'L2',
})

const reconcileItems = ref<FlowReconcileItem[]>([])
const reconcileTotal = ref(0)
const reconcileLoading = ref(false)
const reconcilePersistBusy = ref(false)
const openingSeedBusy = ref(false)
const lineageLoading = ref(false)
const lineageActionBusy = ref(false)
const lineageItems = ref<
  Array<{
    release_id: string
    file_id?: string
    target_domain?: string
    clean_rows?: number
    released_at?: string
  }>
>([])
const supersedeNewer = ref('')
const supersedeOlder = ref('')
const lineageRebuildId = ref('')
const lineageRevokeOnly = ref(false)
const reconcileByClass = ref<Record<string, number>>({})

const reconcileCards = computed(() => [
  { key: 'inv_only', label: '库存有流水无', value: reconcileByClass.value.inv_only ?? 0 },
  { key: 'flow_only', label: '流水有库存无', value: reconcileByClass.value.flow_only ?? 0 },
  { key: 'mismatch', label: '两边有但不符', value: reconcileByClass.value.mismatch ?? 0 },
  { key: 'opening', label: '期初已填行', value: reconcileByClass.value.opening_populated_rows ?? 0 },
])

function gapClassLabel(cls: string) {
  const map: Record<string, string> = {
    inv_only: '库存有流水无',
    flow_only: '流水有库存无',
    mismatch: '两边有但不符',
  }
  return map[cls] || cls
}

function gapClassHint(cls: string) {
  const map: Record<string, string> = {
    inv_only: '库存有流水无：流水覆盖缺失',
    flow_only: '流水有库存无：编码对不上',
    mismatch: '两边有但数额不符',
  }
  return map[cls] || cls
}

/** HG-3.4 行着色：类别差异可视化（inv_only 红 / flow_only 黄 / mismatch 橙）。 */
function gapRowClass({ row }: { row: { gap_class?: string } }) {
  return row.gap_class ? `gap-${row.gap_class}` : ''
}

function applyReconcilePayload(res: {
  items?: FlowReconcileItem[]
  total: number
  threshold: number
  formula?: string
  note?: string
  by_class?: Record<string, number>
  material_id_overlap?: number
  opening_populated_rows?: number
}) {
  reconcileItems.value = res.items || []
  reconcileTotal.value = res.total
  const bc = res.by_class || {}
  reconcileByClass.value = { ...bc, opening_populated_rows: res.opening_populated_rows ?? 0 }
}

function flowTypeLabel(v?: string | null): string {
  if (String(v || '').toUpperCase() === 'IN') return '入库'
  if (String(v || '').toUpperCase() === 'OUT') return '出库'
  return v || '—'
}

/** 标准字段显示名：ignore 显示为「忽略」，其余按中文映射，未知字段保留原名。 */
function stdFieldLabel(f: string | null | undefined) {
  if (!f) return '未选择'
  if (f === 'ignore') return '忽略'
  return fieldzh(f)
}

/** 原始表头展示：已知英文字段名译成中文，未知保持原样。 */
function headerLabel(h?: string | null) {
  const s = String(h ?? '').trim()
  if (!s) return '—'
  return fieldzh(s)
}

/** 工作表名展示：内部名 tabular / Sheet1 等译成中文。 */
function sheetLabel(s?: string | null) {
  const raw = String(s ?? '').trim()
  if (!raw) return '—'
  const map: Record<string, string> = {
    tabular: '表格数据',
    Sheet1: '工作表1',
    sheet1: '工作表1',
  }
  return map[raw] || raw
}

/** 文件列：优先文件名，其次 file_id。 */
function fileLabel(row: { source_file?: string | null; filename?: string | null; file_id?: string | null }) {
  const name = String(row.source_file || row.filename || '').trim()
  if (name) return name
  const fid = String(row.file_id || '').trim()
  return fid || '—'
}

/** 当前建议值不在标准字段列表时，补一条选项以免下拉显示英文原值。 */
function extraSelectField(f?: string | null) {
  const v = String(f ?? '').trim()
  if (!v || v === 'ignore') return false
  return !stdFields.value.includes(v)
}

/** AI/模型状态显示名：把 model_state / llm_state 等翻译为中文。 */
function modelStateLabel(s?: string | null) {
  const map: Record<string, string> = {
    not_attempted: '未尝试',
    rule_dict_hit: '规则字典命中',
    embed_high_confidence: '高置信匹配',
    local_model_unavailable: '本地模型不可用',
    circuit_open: '模型熔断',
    llm_analysis_available: '智能建议成功',
    llm_output_invalid: '智能建议输出无效',
    llm_invocation_failed: '智能建议调用失败',
    fallback: '降级方案',
    none: '未运行',
    queued: '排队中',
    done: '已完成',
    failed: '失败',
    ok: '成功',
  }
  return map[String(s ?? '')] || String(s ?? '—')
}

/** 流水解析角色显示名：fast / big 翻译为中文。 */
function llmRoleLabel(r?: string | null) {
  const map: Record<string, string> = { fast: '快速模型', big: '大模型' }
  return map[String(r ?? '')] || String(r ?? '—')
}

/** 主数据冲突原因 / 候选 why 显示名。 */
function conflictLabel(c?: string | null) {
  const map: Record<string, string> = {
    code_same_name_diff: '编码同名称异',
    name_same_code_diff: '名称同编码异',
    spec_diff: '规格不同',
  }
  return map[String(c ?? '')] || String(c ?? '')
}

/** 表头映射原因显示名。 */
function reasonLabel(r?: string | null) {
  const map: Record<string, string> = {
    unmapped: '未匹配到标准字段',
    conflict: '与已有规则冲突',
    dict_conflict: '与已有规则冲突',
    multi_candidate: '存在多个候选',
    low_confidence: '匹配置信度低',
  }
  return map[String(r ?? '')] || String(r ?? '—')
}

/** 业务域中文名。 */
function domainZh(d?: string | null) {
  const map: Record<string, string> = {
    inventory: '库存',
    asset: '资产',
    demand: '需求',
    stock_flow: '出入库流水',
    flow: '出入库流水',
  }
  return map[String(d ?? '')] || String(d ?? '')
}

/** 规则学习候选 reason_code / fingerprint.code 中文名。 */
function reasonCodeZh(code?: string | null) {
  const map: Record<string, string> = {
    EMPTY_ROW: '整行空白',
    MISSING_REQUIRED: '必填字段为空',
    MISSING_COL: '缺少必填字段',
    REQUIRED: '必填校验失败',
    REQUIRED_UNMAPPED: '必填列未映射',
    VALUE_RANGE: '取值越界',
    UNKNOWN_HEADER: '未知表头',
    TYPE_ERROR: '类型错误（应为数字）',
    DATE_FORMAT: '日期格式不统一',
    EMPTY_SERIAL: '出厂编号为空或占位',
    CELL_MARKER: '单元格标记异常',
    OTHER: '其他质量问题',
  }
  const c = String(code ?? '')
  return map[c] || gateLabel(c) || c
}

/** 从候选提案中取原因编码（优先 reason_code，其次 fingerprint.code）。 */
function proposalCode(p?: Record<string, unknown>): string {
  if (!p) return ''
  const direct = String(p.reason_code || '')
  if (direct) return direct
  const fp = p.fingerprint
  if (typeof fp === 'string') {
    try {
      return String((JSON.parse(fp) as { code?: string }).code || '')
    } catch {
      return ''
    }
  }
  if (fp && typeof fp === 'object') {
    return String((fp as { code?: string }).code || '')
  }
  return ''
}

/** 数据校验方式的用户可读描述：按原因编码优先，避免「资产名称必须为正数」这类错位表述。 */
function checkDesc(p?: Record<string, unknown>): string {
  const code = proposalCode(p)
  if (['MISSING_REQUIRED', 'MISSING_COL', 'REQUIRED'].includes(code)) return '不能为空'
  if (code === 'VALUE_RANGE') return '取值须为正数'
  const checkZh: Record<string, string> = {
    required: '不能为空',
    numeric_positive: '取值须为正数',
  }
  return checkZh[String(p?.check_type || '')] || String(p?.check_type || '')
}

/** 规则学习候选提案摘要：全中文，按 kind 组织成一句用户能看懂的话。 */
function proposalLabel(p?: Record<string, unknown>) {
  if (!p) return '—'
  const kind = String(p.kind || '')
  const dom = domainZh(String(p.domain || ''))
  if (kind === 'map_alias') {
    const from = String(p.header || '')
    const to = stdFieldLabel(String(p.suggested_std_field || ''))
    return `表头映射：${dom}「${from || '未命名表头'}」→「${to}」`
  }
  if (kind === 'value_rule') {
    const field = stdFieldLabel(String(p.std_field || ''))
    return `数据校验：${dom}「${field}」${checkDesc(p)}`
  }
  const code = proposalCode(p)
  const zh = reasonCodeZh(code)
  const header = String(p.header || '')
  const headPart = header ? `「${fieldzh(header)}」` : ''
  return `人工复核：${dom}${headPart}${zh || '存在异常'}`
}

/** 规则学习候选「建议」列文案：全中文。 */
function proposalHint(p?: Record<string, unknown>) {
  if (!p) return '—'
  const kind = String(p.kind || '')
  if (kind === 'map_alias') return '确认映射后写入字段叫法规则，后续同类表头自动识别'
  if (kind === 'value_rule') return '该字段高频异常，建议新增数据校验规则（确认后生效）'
  if (kind === 'review') return '需人工复核源数据，确认后决定是否采纳'
  return String(p.hint || '确认后才生效')
}

/** 决策/状态显示名：把 accept/amend/ignore/proposed 等翻译为中文。 */
function decisionLabel(d: string) {
  const map: Record<string, string> = {
    accept: '接受',
    amend: '修正',
    ignore: '忽略',
    approve: '批准',
    merge: '合并',
    reject: '拒绝',
    proposed: '待确认',
    accepted: '已接受',
    rejected: '已拒绝',
    pending: '待处理',
  }
  return map[d] || d
}

const PARSE_SOURCE_ZH: Record<string, string> = {
  rule: '规则解析',
  llm: '大模型解析',
  manual: '人工录入',
  example: '示例',
}

function summarizeSuggest(row: FlowPendingItem): string {
  const s = (row.suggested || {}) as Record<string, unknown>
  const qty = s.quantity
  const date = s.flow_date
  const person = s.person
  const src = s.parse_source
  const srcZh = src ? PARSE_SOURCE_ZH[String(src)] || String(src) : ''
  return [srcZh, date, qty != null ? `数量=${qty}` : null, person].filter(Boolean).join(' · ') || '—'
}

function onFlowSelect(rowsSel: FlowPendingItem[]) {
  selectedPending.value = rowsSel
}

async function onTab(name: string | number) {
  const n = String(name)
  emit('tab-change', n)
  if (n === 'map') {
    await loadMapPending()
  } else if (n === 'rulelearn') {
    await loadRuleLearn()
  } else if (n === 'master') {
    await loadMasterPending()
  } else if (n === 'flow') {
    await Promise.all([loadFlowPending(), loadFlowStats()])
  } else if (n === 'reconcile') {
    await loadReconcile()
    await loadLineageReleases()
  }
}

async function loadRuleLearn() {
  rlLoading.value = true
  try {
    rlItems.value = (await listRuleLearnCandidates(50)).items || []
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    rlLoading.value = false
  }
}

async function runRuleLearn() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  rlBusy.value = true
  try {
    const out = await proposeRuleLearn({ min_count: 2 })
    ElMessage.success(`扫描 ${out.scanned_groups} 组，新建 ${out.created}`)
    await loadRuleLearn()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    rlBusy.value = false
  }
}

function openCreateRule() {
  if (!requireOpsToken()) return
  createRule.rule_type = 'field_alias'
  createRule.header = ''
  createRule.std_field = ''
  createRule.check_type = 'numeric_positive'
  createRule.scope_note = ''
  createRuleVisible.value = true
}

async function submitCreateRule() {
  createRuleBusy.value = true
  try {
    await createRuleLearnCandidate({
      rule_type: createRule.rule_type,
      header: createRule.header,
      std_field: createRule.std_field,
      check_type: createRule.check_type,
      scope_note: createRule.scope_note,
    })
    createRuleVisible.value = false
    ElMessage.success('已写入待确认规则')
    await loadRuleLearn()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    createRuleBusy.value = false
  }
}

async function acceptRl(row: { id: number; proposal?: Record<string, unknown> }) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  let std_field: string | undefined
  const kind = row.proposal?.kind
  if (kind === 'map_alias') {
    std_field = String(row.proposal?.suggested_std_field || row.proposal?.std_field || '')
    if (!std_field) {
      ElMessage.warning('请先在新建规则时填写标准字段')
      return
    }
  }
  let previewNote = ''
  try {
    const preview = await confirmRuleLearn(row.id, {
      decision: 'accepted',
      std_field,
      dry_run: true,
    })
    previewNote = [
      `影响约 ${preview.affected_rows ?? row.proposal?.count ?? 0} 行阻塞样本`,
      preview.will_write ? `将写入 ${preview.will_write}` : '不写入规则',
      preview.warning || '',
    ]
      .filter(Boolean)
      .join('；')
  } catch {
    previewNote = `影响约 ${row.proposal?.count ?? 0} 行；规则变更不会自动回刷已入库历史行`
  }
  try {
    await ElMessageBox.confirm(
      `采用该规则？\n${previewNote}`,
      '确认采用',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await confirmRuleLearn(row.id, { decision: 'accepted', std_field })
    ElMessage.success('已采用')
    await loadRuleLearn()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function rejectRl(id: number) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  try {
    await confirmRuleLearn(id, { decision: 'rejected' })
    ElMessage.success('未采用')
    await loadRuleLearn()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function loadMapPending() {
  mapPendingLoading.value = true
  try {
    const res = await listMapPending({
      status: 'pending',
      limit: mapPageSize.value,
      offset: (mapPage.value - 1) * mapPageSize.value,
    })
    mapPending.value = res.items || []
    mapPendingTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    mapPendingLoading.value = false
  }
}

async function confirmMapRow(row: MapPendingItem) {
  if (!requireOpsToken()) return
  const ignore = !row.suggested_field || row.suggested_field === 'ignore'
  const msg = ignore
    ? `确认处理「${row.header}」？将忽略该表头。`
    : `确认处理「${row.header}」→ ${stdFieldLabel(row.suggested_field)}？`
  try {
    await ElMessageBox.confirm(msg, '确认处理', { type: 'warning' })
  } catch {
    return
  }
  try {
    await confirmMapPending({
      pending_id: row.pending_id,
      decision: ignore ? 'ignore' : 'accept',
      std_field: ignore ? 'ignore' : row.suggested_field || undefined,
    })
    ElMessage.success('已确认处理')
    await loadMapPending()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

function candidateLabel(c: { material_code?: string; material_name?: string }) {
  const code = (c.material_code || '').trim()
  const name = (c.material_name || '').trim()
  if (code && name) return `${code} · ${name}`
  if (name) return name
  if (code) return code
  return '未维护编码'
}

async function loadMasterPending() {
  masterPendingLoading.value = true
  try {
    const res = await listMasterPending({
      status: 'pending',
      limit: masterPageSize.value,
      offset: (masterPage.value - 1) * masterPageSize.value,
    })
    masterPending.value = (res.items || []).map((i) => ({ ...i }))
    masterPendingTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    masterPendingLoading.value = false
  }
}

async function runMasterPropose() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  masterProposeBusy.value = true
  try {
    const res = await proposeMasterPending(500)
    ElMessage.success(`扫描 ${res.scanned}，入队 ${res.enqueued}，刷新 ${res.refreshed}`)
    await loadMasterPending()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    masterProposeBusy.value = false
  }
}

async function decideMaster(
  row: MasterPendingItem & { _mergeTo?: string },
  decision: 'approve' | 'reject' | 'merge',
) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  if (decision === 'merge' && !row._mergeTo && !(row.candidates || []).length) {
    ElMessageBox.alert(
      '当前没有可合并的候选物资。信息有误请点「修正」，确认是新物资请点「批准」，不需要则点「拒绝」。',
      '无法合并',
      { type: 'info' },
    )
    return
  }
  if (decision === 'merge' && !row._mergeTo) {
    ElMessage.warning('请先选择要合并到的候选物资')
    return
  }
  const label = row.material_name || row.material_code || '未维护编码'
  try {
    await ElMessageBox.confirm(
      `${decisionLabel(decision)}「${label}」？将经写入器写业务库。`,
      '主数据确认门',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await confirmMasterPending({
      pending_id: row.pending_id,
      decision,
      merge_to_material_id: decision === 'merge' ? row._mergeTo : undefined,
    })
    notifyBrowse('已确认', 'dim_material')
    await loadMasterPending()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

function openAmendMaster(row: MasterPendingItem & { _mergeTo?: string }) {
  if (!requireOpsToken()) return
  amendMasterRow.value = row
  amendMaster.material_code = String(row.material_code || '')
  amendMaster.material_name = String(row.material_name || '')
  amendMaster.spec = String(row.spec || '')
  amendMaster.unit = String(row.unit || '')
  amendMaster.category = String(row.category || '')
  amendMasterVisible.value = true
}

async function submitAmendMaster() {
  const row = amendMasterRow.value
  if (!row) return
  if (!amendMaster.material_name.trim() && !amendMaster.material_code.trim()) {
    ElMessage.warning('至少填写物资名称或物资编码')
    return
  }
  amendMasterBusy.value = true
  try {
    await confirmMasterPending({
      pending_id: row.pending_id,
      decision: 'approve',
      material_patch: {
        material_code: amendMaster.material_code.trim(),
        material_name: amendMaster.material_name.trim(),
        spec: amendMaster.spec.trim(),
        unit: amendMaster.unit.trim(),
        category: amendMaster.category.trim(),
      },
    })
    amendMasterVisible.value = false
    notifyBrowse('已修正并批准', 'dim_material')
    await loadMasterPending()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    amendMasterBusy.value = false
  }
}

async function onFlowFilter() {
  flowPage.value = 1
  await loadFlowPending()
}

async function loadFlowPending() {
  flowLoading.value = true
  try {
    const offset = (flowPage.value - 1) * flowPageSize.value
    const res = await listFlowPending({
      status: flowStatus.value,
      limit: flowPageSize.value,
      offset,
      parse_level: flowLevelFilter.value,
    })
    flowItems.value = res.items
    flowTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowLoading.value = false
  }
}

async function loadFlowStats() {
  try {
    const s = await fetchFlowStats()
    Object.assign(flowStats, s)
  } catch {
    /* optional */
  }
}

async function decideOne(
  row: FlowPendingItem,
  decision: 'accept' | 'ignore',
  overwrite = false,
) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  flowBatchBusy.value = true
  try {
    const res = await confirmFlowPending({
      pending_id: row.pending_id,
      decision,
      note: overwrite ? 'ui-overwrite' : `ui-${decision}`,
      overwrite,
    })
    if (res.code === 'FLOW_EXAMPLE_CONFLICT' || (!res.ok && res.conflict)) {
      ElMessage.warning('与已有示例冲突，可切到冲突状态后「覆盖接受」')
    } else if (!res.ok) {
      ElMessage.error(res.code || '失败')
    } else {
      ElMessage.success(
        decision === 'accept' ? (overwrite ? '已覆盖接受' : '已接受') : '已忽略',
      )
    }
    await Promise.all([loadFlowPending(), loadFlowStats()])
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function batchAccept() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  const ids = selectedPending.value.map((x) => x.pending_id)
  if (!ids.length) return
  const overwrite = flowStatus.value === 'conflict'
  try {
    await ElMessageBox.confirm(
      overwrite
        ? `批量覆盖接受 ${ids.length} 条？将更新已有流水拆解示例。`
        : `批量接受 ${ids.length} 条？将回写流水拆解示例。`,
      overwrite ? '覆盖接受' : '批量接受',
      { type: 'warning' },
    )
  } catch {
    return
  }
  flowBatchBusy.value = true
  let ok = 0
  let conflict = 0
  try {
    for (const id of ids) {
      const res = await confirmFlowPending({
        pending_id: id,
        decision: 'accept',
        note: overwrite ? 'ui-batch-overwrite' : 'ui-batch',
        overwrite,
      })
      if (res.ok) ok += 1
      else if (res.code === 'FLOW_EXAMPLE_CONFLICT' || res.conflict) conflict += 1
    }
    ElMessage.success(`完成：接受 ${ok}/${ids.length}` + (conflict ? `，冲突 ${conflict}` : ''))
    notifyBrowse('已回写，可到台账验证', 'fact_stock_flow')
    await Promise.all([loadFlowPending(), loadFlowStats()])
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function batchIgnore() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  const ids = selectedPending.value.map((x) => x.pending_id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`批量忽略 ${ids.length} 条？记录为需要人工确认的负例。`, '批量忽略', {
      type: 'warning',
    })
  } catch {
    return
  }
  flowBatchBusy.value = true
  let ok = 0
  try {
    for (const id of ids) {
      const res = await confirmFlowPending({
        pending_id: id,
        decision: 'ignore',
        note: 'ui-batch-ignore',
      })
      if (res.ok) ok += 1
    }
    ElMessage.success(`已忽略 ${ok}/${ids.length}`)
    await Promise.all([loadFlowPending(), loadFlowStats()])
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function runFlowSuggestSelected() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  flowSuggestBusy.value = true
  let ok = 0
  try {
    for (const row of selectedPending.value) {
      // PolicyRouter primary=fast; omit force_role
      const res = await suggestFlowPending({ pending_id: row.pending_id })
      if (res && (res as { ok?: boolean }).ok) ok += 1
    }
    ElMessage.success(`智能建议完成 ${ok}/${selectedPending.value.length}`)
    await loadFlowPending()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowSuggestBusy.value = false
  }
}

async function runFlowSuggestQueue() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  const limit = flowSuggestLimit.value
  try {
    await ElMessageBox.confirm(
      `对最多 ${limit} 条尚未建议的待确认项运行策略路由（快速模型→必要时升级）？仅写建议，不改业务库。`,
      '队列批处理',
      { type: 'warning' },
    )
  } catch {
    return
  }
  flowDrainBusy.value = true
  try {
    const res = await suggestFlowPending({ limit })
    const body = res as { processed?: number; items?: unknown[]; ok?: boolean; count?: number }
    const processed =
      body.processed ??
      body.count ??
      (Array.isArray(body.items) ? body.items.length : body.ok ? 1 : 0)
    ElMessage.success(`队列批处理完成（已处理 ${processed} 条）`)
    await Promise.all([loadFlowPending(), loadFlowStats()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowDrainBusy.value = false
  }
}

function openAmend(row: FlowPendingItem) {
  amendRow.value = row
  const s = (row.suggested || {}) as Record<string, unknown>
  amendForm.flow_type = String(s.flow_type || row.flow_type || 'OUT')
  amendForm.flow_date = s.flow_date == null ? '' : String(s.flow_date)
  amendForm.quantity = s.quantity == null ? '' : String(s.quantity)
  amendForm.unit = s.unit == null ? '' : String(s.unit)
  amendForm.person = s.person == null ? '' : String(s.person)
  amendForm.purpose = s.purpose == null ? '' : String(s.purpose)
  amendForm.parse_level = String(s.parse_level || row.parse_level || 'L2')
  amendNote.value = ''
  amendVisible.value = true
}

async function submitAmend() {
  if (!amendRow.value) return
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  const qtyRaw = amendForm.quantity.trim()
  let quantity: number | null = null
  if (qtyRaw !== '') {
    const n = Number(qtyRaw)
    if (Number.isNaN(n)) {
      ElMessage.warning('数量须为数字')
      return
    }
    quantity = n
  }
  flowBatchBusy.value = true
  try {
    await confirmFlowPending({
      pending_id: amendRow.value.pending_id,
      decision: 'amend',
      note: amendNote.value || 'ui-amend',
      corrected: {
        flow_type: amendForm.flow_type,
        flow_date: amendForm.flow_date.trim() || null,
        quantity,
        unit: amendForm.unit.trim() || null,
        person: amendForm.person.trim() || null,
        purpose: amendForm.purpose.trim() || null,
        parse_level: amendForm.parse_level,
        parse_source: 'manual',
        remark: amendRow.value.text_raw,
      },
    })
    ElMessage.success('已修正并回写示例')
    amendVisible.value = false
    await Promise.all([loadFlowPending(), loadFlowStats()])
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function loadReconcile() {
  reconcileLoading.value = true
  try {
    const res = await flowReconcile()
    applyReconcilePayload(res)
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    reconcileLoading.value = false
  }
}

async function seedOpening() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  try {
    await ElMessageBox.confirm(
      '对「仅有库存、无流水」的物资写入期初数量=库存数量（经写入器）。不处理已有流水的物资。确认？',
      '期初种子',
      { type: 'warning' },
    )
  } catch {
    return
  }
  openingSeedBusy.value = true
  try {
    const dry = await flowOpeningSeed(true)
    const n = dry.would_update ?? 0
    if (!n) {
      ElMessage.info('无需更新（已无「仅有库存、无流水」的候选）')
      await loadReconcile()
      return
    }
    const res = await flowOpeningSeed(false)
    ElMessage.success(`已写入期初 ${res.updated ?? 0} 行`)
    await loadReconcile()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    openingSeedBusy.value = false
  }
}

async function loadLineageReleases() {
  lineageLoading.value = true
  try {
    const res = await listLineageReleases({ limit: 20 })
    lineageItems.value = res.items || []
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    lineageLoading.value = false
  }
}

async function runReleaseSupersede() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  const newer = supersedeNewer.value.trim()
  const older = supersedeOlder.value.trim()
  if (!newer || !older) {
    ElMessage.warning('请填写较新与较旧两个 release_id')
    return
  }
  try {
    await ElMessageBox.confirm(
      dangerousConfirmMessage({
        objectId: `newer=${newer} / older=${older}`,
        action: '版本取代（release supersede）',
        impact: '较旧版本将被标记为被取代，审计链与数据成果中的版本关系会更新',
      }),
      '危险操作确认',
      { type: 'warning', confirmButtonText: '确认取代', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  lineageActionBusy.value = true
  try {
    await releaseSupersede(newer, older)
    ElMessage.success('版本取代已完成')
    await loadLineageReleases()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    lineageActionBusy.value = false
  }
}

async function runLineageRebuild() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  const rid = lineageRebuildId.value.trim()
  if (!rid) {
    ElMessage.warning('请填写 release_id')
    return
  }
  const action = lineageRevokeOnly.value ? '仅撤销发布（revoke_only）' : '撤销并重建血缘（lineage rebuild）'
  try {
    await ElMessageBox.confirm(
      dangerousConfirmMessage({
        objectId: rid,
        action,
        impact: lineageRevokeOnly.value
          ? '撤销该发布版本关联的业务行，不自动重建'
          : '撤销该发布版本并尝试按规则重建关联数据，可能影响库存/流水事实表',
      }),
      '危险操作确认',
      { type: 'error', confirmButtonText: '确认执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  lineageActionBusy.value = true
  try {
    const res = await lineageRebuild({ release_id: rid, revoke_only: lineageRevokeOnly.value })
    ElMessage.success(
      lineageRevokeOnly.value
        ? `已撤销 release ${res.release_id || rid}`
        : `重建完成：${res.rows ?? 0} 行`,
    )
    await loadLineageReleases()
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    lineageActionBusy.value = false
  }
}

async function persistReconcile() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning(TOKEN_HINT)
    return
  }
  try {
    await ElMessageBox.confirm(
      dangerousConfirmMessage({
        objectId: 'fact_stock_flow 对账差异表',
        action: '重算并落库对账差异',
        impact: `将删除并重建对账差异表（当前清单 ${reconcileTotal.value} 行），供「对账差异数」指标读取`,
      }),
      '危险操作确认',
      { type: 'warning', confirmButtonText: '确认落库', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  reconcilePersistBusy.value = true
  try {
    const res = await flowReconcilePersist()
    applyReconcilePayload(res)
    notifyBrowse(`已落库 ${res.total} 条差异`, 'fact_stock_flow')
    notifyQueueChanged()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    reconcilePersistBusy.value = false
  }
}

function exportReconcile() {
  const header = [
    'gap_class',
    'material_id',
    'stock_qty',
    'opening_qty',
    'expected_net',
    'flow_net',
    'gap',
    'source_file',
  ]
  const lines = [header.join(',')]
  for (const r of reconcileItems.value) {
    lines.push(
      header
        .map((k) => {
          const v = (r as Record<string, unknown>)[k]
          const s = v == null ? '' : String(v)
          return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
        })
        .join(','),
    )
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `库存对账_当前结果.csv`
  a.click()
  URL.revokeObjectURL(url)
}

watch(
  () => props.initialTab,
  async (v) => {
    if (!v || v === tab.value) return
    tab.value = v
    await onTab(v)
  },
)

onMounted(async () => {
  try {
    const sf = await listStdFields()
    stdFields.value = sf.fields
  } catch {
    /* keep default */
  }
  tab.value = props.initialTab || 'map'
  await onTab(tab.value)
})

onUnmounted(() => {
  window.removeEventListener('focus', refreshTokenState)
  window.removeEventListener('storage', refreshTokenState)
  window.removeEventListener('ops-settings-changed', refreshTokenState)
})
</script>

<style scoped>
.govern { display: flex; flex-direction: column; gap: 16px; width: 100%; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.outer-hint { color: #606266; font-size: 13px; line-height: 1.6; margin: 0; }
.result-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cand { cursor: pointer; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.pager { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 24px; font-weight: 600; margin-top: 4px; }
.danger-hint { color: #909399; font-size: 13px; margin: 0 0 12px; line-height: 1.5; }
.danger-form { margin-top: 16px; }
/* HG-3.4 库存对账行着色（scoped + :deep 作用于 el-table 行） */
:deep(.gap-inv_only) { background: #fef2f2; }
:deep(.gap-flow_only) { background: #fffbeb; }
:deep(.gap-mismatch) { background: #fff7ed; }
</style>
