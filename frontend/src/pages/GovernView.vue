<template>
  <div class="govern">
    <el-dialog v-model="guideVisible" title="治理向导" width="520px">
      <p>本页处理机器不确定项，按顺序操作：</p>
      <ol>
        <li>表头映射：确认低置信字段映射</li>
        <li>规则学习：从阻塞明细聚合候选规则</li>
        <li>主数据待审：合并/批准独立物料</li>
        <li>流水解析：确认 L2/L3 拆解</li>
        <li>勾稽差异：查看差异并补录（允许非零）</li>
      </ol>
      <template #footer>
        <el-button type="primary" @click="closeGuide">知道了</el-button>
      </template>
    </el-dialog>

    <el-tabs v-model="tab" @tab-change="onTab">
      <el-tab-pane label="表头映射" name="map" />
      <el-tab-pane label="规则学习" name="rulelearn" />
      <el-tab-pane label="主数据待审" name="master" />
      <el-tab-pane label="流水解析" name="flow" />
      <el-tab-pane label="勾稽差异" name="reconcile" />
    </el-tabs>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="治理中心"
      description="机器不确定的项进队列，人工确认后才写入规则与业务库。大模型只提案、不自动发布。"
    />

    <template v-if="tab === 'rulelearn'">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="规则学习候选（只提案）"
        description="从阻塞明细聚合高频原因 → 确认历史；确认后才写规则字典 / 值规则。"
      />
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>规则学习候选</span>
            <el-space>
              <el-button :loading="rlBusy" type="primary" @click="runRuleLearn">扫描阻塞明细</el-button>
              <el-button link type="primary" @click="loadRuleLearn">刷新</el-button>
            </el-space>
          </div>
        </template>
        <el-table :data="rlItems" v-loading="rlLoading" border size="small" empty-text="无候选">
          <el-table-column prop="id" label="编号" width="70" />
          <el-table-column prop="decision" label="状态" width="90" />
          <el-table-column label="提案" min-width="280">
            <template #default="{ row }">
              <span class="mono">{{ JSON.stringify(row.proposal || {}) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.decision === 'proposed'"
                link
                type="primary"
                @click="acceptRl(row)"
              >
                接受
              </el-button>
              <el-button
                v-if="row.decision === 'proposed'"
                link
                type="danger"
                @click="rejectRl(row.id)"
              >
                拒绝
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- —— 表头映射 —— -->
    <template v-if="tab === 'map'">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="表头映射治理（不可自动发布）"
        description="低置信 / 多候选 / 字典冲突进入映射待定；人工确认后回写规则字典。发布业务库仍须走规整确认门。"
      />

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>待确认映射队列</span>
            <el-space>
              <el-button link type="primary" @click="loadMapPending">刷新</el-button>
            </el-space>
          </div>
        </template>
        <el-table :data="mapPending" v-loading="mapPendingLoading" border size="small" empty-text="暂无待确认">
          <el-table-column prop="header" label="表头" min-width="120" />
          <el-table-column prop="reason" label="原因" width="120" />
          <el-table-column prop="suggested_field" label="建议" width="120" />
          <el-table-column prop="sheet" label="工作表" width="100" />
          <el-table-column prop="file_id" label="文件" width="110" />
          <el-table-column label="候选" min-width="200">
            <template #default="{ row }">
              <el-space wrap>
                <el-tag
                  v-for="c in (row.candidates || []).slice(0, 4)"
                  :key="c.std_field + String(c.score)"
                  size="small"
                  class="cand"
                  @click="row.suggested_field = c.std_field"
                >
                  {{ c.std_field }}{{ c.score != null ? ` ${Number(c.score).toFixed(2)}` : '' }}
                </el-tag>
              </el-space>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-select v-model="row.suggested_field" filterable allow-create size="small" style="width: 110px; margin-right: 4px">
                <el-option v-for="f in stdFields" :key="f" :label="f" :value="f" />
              </el-select>
              <el-button link type="success" @click="decideMapPending(row, 'accept')">接受</el-button>
              <el-button link type="warning" @click="decideMapPending(row, 'amend')">修正</el-button>
              <el-button link type="info" @click="decideMapPending(row, 'ignore')">忽略</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="hint">共 {{ mapPendingTotal }} 条待确认</div>
      </el-card>

      <el-card shadow="never" header="1. 输入表头 → 建议并入队">
        <el-input
          v-model="headersText"
          type="textarea"
          :rows="4"
          placeholder="每行一个表头，或用逗号分隔。例如：&#10;物资编码&#10;物资名称&#10;现有数量&#10;库位号"
        />
        <div class="row-actions">
          <el-button type="primary" :loading="suggestBusy" @click="runSuggest">生成建议</el-button>
          <el-button type="warning" :loading="enqueueBusy" @click="runEnqueue">入队低置信项</el-button>
          <el-button @click="headersText = '物资编码\n物资名称\n现有数量\n库位号\n型号规格'">填入库存示例</el-button>
          <el-tag v-if="suggestMeta.state" size="small" type="info">{{ suggestMeta.state }}</el-tag>
          <el-tag v-if="suggestMeta.invoked != null" size="small">
            大模型 {{ suggestMeta.invoked ? '调用' : '跳过' }}
          </el-tag>
          <el-tag v-if="suggestMeta.latency != null" size="small" type="warning">
            {{ suggestMeta.latency }} ms
          </el-tag>
        </div>
        <p v-if="hint" class="hint">{{ hint }}</p>
      </el-card>

      <el-card v-if="rows.length" shadow="never" header="2. 人工核对 / 修改">
        <el-table :data="rows" border size="small" style="width: 100%">
          <el-table-column prop="header" label="表头" min-width="160" />
          <el-table-column label="建议字段" width="200">
            <template #default="{ row }">
              <el-select v-model="row.std_field" filterable allow-create style="width: 100%">
                <el-option v-for="f in stdFields" :key="f" :label="f" :value="f" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="候选（向量匹配）" min-width="260">
            <template #default="{ row }">
              <el-space wrap>
                <el-tag
                  v-for="c in row.candidates.slice(0, 4)"
                  :key="c.std_field + c.score"
                  size="small"
                  class="cand"
                  @click="row.std_field = c.std_field"
                >
                  {{ c.std_field }} {{ c.score.toFixed(2) }}
                </el-tag>
              </el-space>
            </template>
          </el-table-column>
        </el-table>

        <div class="row-actions">
          <el-input v-model="note" placeholder="确认备注（可选）" style="max-width: 360px" />
          <el-button type="success" :loading="confirmBusy" @click="runConfirm">
            确认回写规则字典
          </el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>已确认规则字典</span>
            <el-button link type="primary" @click="loadRules">刷新</el-button>
          </div>
        </template>
        <el-table :data="rules" v-loading="rulesLoading" size="small" border style="width: 100%">
          <el-table-column prop="header" label="表头" min-width="140" />
          <el-table-column prop="std_field" label="标准字段" width="140" />
          <el-table-column prop="hits" label="命中" width="70" />
          <el-table-column prop="source" label="来源" width="120" />
          <el-table-column prop="confirmed_by" label="确认人" width="120" />
          <el-table-column prop="created_at" label="时间" width="170" />
        </el-table>
        <div class="hint">共 {{ rulesTotal }} 条</div>
      </el-card>
    </template>

    <!-- —— 主数据待审 —— -->
    <template v-else-if="tab === 'master'">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="主数据待审（三级解析 → 人工确认）"
        description="扫描主数据表中三级解析的独立物料入待审队列；审批/合并经写入器写业务库并记审计。冲突仅进人工，不可自动发布。"
      />

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>待审队列</span>
            <el-space>
              <el-button type="primary" :loading="masterProposeBusy" @click="runMasterPropose">
                扫描入队
              </el-button>
              <el-button link type="primary" @click="loadMasterPending">刷新</el-button>
            </el-space>
          </div>
        </template>
        <el-table :data="masterPending" v-loading="masterPendingLoading" border size="small" empty-text="暂无待审">
          <el-table-column prop="material_code" label="编码" width="120" show-overflow-tooltip />
          <el-table-column prop="material_name" label="名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="spec" label="规格" width="120" show-overflow-tooltip />
          <el-table-column prop="match_level" label="级别" width="80" />
          <el-table-column prop="conflict_type" label="冲突" width="150" show-overflow-tooltip />
          <el-table-column prop="source_file" label="来源" width="120" show-overflow-tooltip />
          <el-table-column label="候选" min-width="180">
            <template #default="{ row }">
              <el-space wrap>
                <el-tag
                  v-for="c in (row.candidates || []).slice(0, 3)"
                  :key="String(c.material_id) + String(c.why)"
                  size="small"
                  class="cand"
                  @click="row._mergeTo = c.material_id"
                >
                  {{ c.material_code || c.material_id }}{{ c.why ? ` · ${c.why}` : '' }}
                </el-tag>
              </el-space>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button link type="success" @click="decideMaster(row, 'approve')">批准</el-button>
              <el-button link type="warning" @click="decideMaster(row, 'merge')">合并</el-button>
              <el-button link type="info" @click="decideMaster(row, 'reject')">拒绝</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="hint">共 {{ masterPendingTotal }} 条待审</div>
      </el-card>
    </template>

    <!-- —— 流水解析 —— -->
    <template v-else-if="tab === 'flow'">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="流水解析确认（需人工确认）"
        description="接受/修正/忽略会回写流水拆解示例；不会直接改业务库。大模型建议仅预填，须人工确认。"
      />

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>质量快照</span>
            <el-button link type="primary" @click="loadFlowStats">刷新</el-button>
          </div>
        </template>
        <el-space wrap>
          <el-tag>已发布 {{ flowStats.published_total ?? '—' }}</el-tag>
          <el-tag>规则直出 {{ flowStats.published_by_level?.L1 ?? 0 }}</el-tag>
          <el-tag type="warning">规则+校验 {{ flowStats.published_by_level?.L2 ?? 0 }}</el-tag>
          <el-tag type="danger">模型兜底 {{ flowStats.published_by_level?.L3 ?? 0 }}</el-tag>
          <el-tag>规则直出占比 {{ flowStats.l1_ratio ?? '—' }}</el-tag>
          <el-tag type="info">待确认 {{ flowStats.pending ?? '—' }}</el-tag>
          <el-tag
            v-for="(n, lvl) in flowStats.pending_by_level || {}"
            :key="'p'+lvl"
            size="small"
            type="warning"
          >
            待确认 {{ lvl }}: {{ n }}
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
                placeholder="级别"
                style="width: 100px"
                @change="onFlowFilter"
              >
                <el-option label="L1" value="L1" />
                <el-option label="L2" value="L2" />
                <el-option label="L3" value="L3" />
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
                队列批处理（大模型）
              </el-button>
              <el-button
                type="primary"
                plain
                :loading="flowSuggestBusy"
                :disabled="!selectedPending.length"
                @click="runFlowSuggestSelected"
              >
                大模型建议选中
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
          <el-table-column prop="parse_level" label="级别" width="70" />
          <el-table-column prop="flow_type" label="方向" width="70" />
          <el-table-column prop="source_sheet" label="工作表" width="120" show-overflow-tooltip />
          <el-table-column prop="text_raw" label="原文" min-width="220" show-overflow-tooltip />
          <el-table-column label="建议摘要" min-width="200">
            <template #default="{ row }">
              <span class="mono">{{ summarizeSuggest(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="llm_state" label="大模型" width="90" />
          <el-table-column prop="llm_role" label="角色" width="70" />
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

      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>自学习示例池（流水拆解示例）</span>
            <el-button link type="primary" @click="loadFlowExamples">刷新</el-button>
          </div>
        </template>
        <el-table :data="flowExamples" v-loading="examplesLoading" size="small" border>
          <el-table-column prop="level" label="级别" width="70" />
          <el-table-column prop="text_norm" label="原文归一" min-width="220" show-overflow-tooltip />
          <el-table-column prop="hits" label="命中" width="70" />
          <el-table-column prop="confirmed_by" label="确认人" width="120" />
          <el-table-column prop="updated_at" label="更新" width="170" />
        </el-table>
        <div class="hint">共 {{ examplesTotal }} 条（只读）</div>
      </el-card>

      <el-dialog v-model="amendVisible" title="修正流水建议" width="560px" destroy-on-close>
        <el-form label-width="88px">
          <el-form-item label="原文">
            <div class="hint">{{ amendRow?.text_raw }}</div>
          </el-form-item>
          <el-form-item label="方向">
            <el-select v-model="amendForm.flow_type" style="width: 140px">
              <el-option label="IN" value="IN" />
              <el-option label="OUT" value="OUT" />
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
          <el-form-item label="级别">
            <el-select v-model="amendForm.parse_level" style="width: 140px">
              <el-option label="L1" value="L1" />
              <el-option label="L2" value="L2" />
              <el-option label="L3" value="L3" />
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

    <!-- —— 勾稽差异 —— -->
    <template v-else>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="勾稽差异（允许非零）"
        :description="reconcileAlertDesc"
      />
      <el-card shadow="never">
        <template #header>
          <div class="result-head">
            <span>差异清单 · {{ reconcileTotal }} 行（阈值 {{ reconcileThreshold }}）</span>
            <el-space>
              <el-button :loading="reconcileLoading" @click="loadReconcile">刷新（只读）</el-button>
              <el-button :loading="openingSeedBusy" @click="seedOpening">期初种子（仅库存无流水）</el-button>
              <el-button type="primary" :loading="reconcilePersistBusy" @click="persistReconcile">
                重算并落库
              </el-button>
              <el-button :disabled="!reconcileItems.length" @click="exportReconcile">导出 CSV</el-button>
            </el-space>
          </div>
        </template>
        <p v-if="reconcileFormula" class="hint mono">{{ reconcileFormula }}</p>
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
          <el-table-column prop="material_id" label="物料编号" min-width="160" show-overflow-tooltip />
          <el-table-column prop="stock_qty" label="库存" width="90" />
          <el-table-column prop="opening_qty" label="期初" width="90" />
          <el-table-column prop="expected_net" label="库存−期初" width="110" />
          <el-table-column prop="flow_net" label="流水净额" width="110" />
          <el-table-column prop="gap" label="差异" width="100" />
          <el-table-column prop="source_file" label="来源" min-width="160" show-overflow-tooltip />
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { ElLink, ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { useRouter } from 'vue-router'
import PagedTable from '@/components/PagedTable.vue'
import {
  confirmFlowPending,
  flowOpeningSeed,
  flowReconcile,
  flowReconcilePersist,
  flowStats as fetchFlowStats,
  formatApiError,
  listFlowExamples,
  listFlowPending,
  listRuleDict,
  listStdFields,
  listMapPending,
  enqueueMapHeaders,
  confirmMapPending,
  mapConfirm,
  mapSuggest,
  suggestFlowPending,
  proposeMasterPending,
  listMasterPending,
  confirmMasterPending,
  proposeRuleLearn,
  listRuleLearnCandidates,
  confirmRuleLearn,
  type FlowPendingItem,
  type FlowReconcileItem,
  type MapPendingItem,
  type MasterPendingItem,
} from '@/api/client'

const router = useRouter()

/** 治理确认成功后提示，并带"去台账浏览验证"快捷链接（ledger-browse LB-3.3）。 */
function notifyBrowse(title: string, table: string) {
  ElNotification({
    title,
    message: h(
      ElLink,
      { type: 'primary', underline: false, onClick: () => router.push(`/browse?table=${table}`) },
      () => '去台账浏览验证',
    ),
    type: 'success',
    duration: 4500,
  })
}

type Row = {
  header: string
  std_field: string
  candidates: Array<{ std_field: string; score: number }>
}

const tab = ref('map')
const guideVisible = ref(false)

function closeGuide() {
  guideVisible.value = false
  localStorage.setItem('govern_guide_seen', '1')
}

const headersText = ref('')
const rows = ref<Row[]>([])
const stdFields = ref<string[]>(['ignore'])
const hint = ref('')
const note = ref('')
const suggestBusy = ref(false)
const enqueueBusy = ref(false)
const confirmBusy = ref(false)
const suggestMeta = ref<{ state?: string; invoked?: boolean; latency?: number }>({})
const rules = ref<Array<Record<string, unknown>>>([])
const rulesTotal = ref(0)
const rulesLoading = ref(false)
const rlItems = ref<
  Array<{ id: number; decision: string; proposal?: Record<string, unknown> }>
>([])
const rlLoading = ref(false)
const rlBusy = ref(false)
const mapPending = ref<MapPendingItem[]>([])
const mapPendingTotal = ref(0)
const mapPendingLoading = ref(false)

const masterPending = ref<Array<MasterPendingItem & { _mergeTo?: string }>>([])
const masterPendingTotal = ref(0)
const masterPendingLoading = ref(false)
const masterProposeBusy = ref(false)

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
const flowExamples = ref<Array<Record<string, unknown>>>([])
const examplesTotal = ref(0)
const examplesLoading = ref(false)

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
const reconcileThreshold = ref(0.01)
const reconcileLoading = ref(false)
const reconcilePersistBusy = ref(false)
const openingSeedBusy = ref(false)
const reconcileFormula = ref('')
const reconcileNote = ref('')
const reconcileClassHint = ref('')
const reconcileByClass = ref<Record<string, number>>({})

const reconcileCards = computed(() => [
  { key: 'inv_only', label: '库存有流水无', value: reconcileByClass.value.inv_only ?? 0 },
  { key: 'flow_only', label: '流水有库存无', value: reconcileByClass.value.flow_only ?? 0 },
  { key: 'mismatch', label: '两边有但不符', value: reconcileByClass.value.mismatch ?? 0 },
  { key: 'opening', label: '期初已填行', value: reconcileByClass.value.opening_populated_rows ?? 0 },
])

const reconcileAlertDesc = computed(() => {
  const base =
    reconcileNote.value ||
    'ΣIN−ΣOUT ≟ 库存−期初；缺期初按 0。已知源头出库缺失率高（维护材料约 79%、备品备件约 98%），差异是常态；本页用于可见、可导出、可补录，不自动轧平。'
  return reconcileClassHint.value ? `${base} ${reconcileClassHint.value}` : base
})

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
  reconcileThreshold.value = res.threshold
  reconcileFormula.value = res.formula || ''
  reconcileNote.value = res.note || ''
  const bc = res.by_class || {}
  reconcileByClass.value = { ...bc, opening_populated_rows: res.opening_populated_rows ?? 0 }
  reconcileClassHint.value =
    `分类 库存有流水无=${bc.inv_only ?? 0} / 流水有库存无=${bc.flow_only ?? 0} / 两边有但不符=${bc.mismatch ?? 0}` +
    ` · 编码交集=${res.material_id_overlap ?? '?'} · 期初已填行=${res.opening_populated_rows ?? '?'}`
}

function parseHeaders(text: string): string[] {
  return text
    .split(/[\n,，;；\t]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function summarizeSuggest(row: FlowPendingItem): string {
  const s = (row.suggested || {}) as Record<string, unknown>
  const qty = s.quantity
  const date = s.flow_date
  const person = s.person
  const src = s.parse_source
  return [src, date, qty != null ? `qty=${qty}` : null, person].filter(Boolean).join(' · ') || '—'
}

function onFlowSelect(rowsSel: FlowPendingItem[]) {
  selectedPending.value = rowsSel
}

async function onTab(name: string | number) {
  const n = String(name)
  if (n === 'map') {
    await Promise.all([loadMapPending(), loadRules()])
  } else if (n === 'rulelearn') {
    await loadRuleLearn()
  } else if (n === 'master') {
    await loadMasterPending()
  } else if (n === 'flow') {
    await Promise.all([loadFlowPending(), loadFlowStats(), loadFlowExamples()])
  } else if (n === 'reconcile') {
    await loadReconcile()
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
    ElMessage.warning('请先填写操作令牌')
    return
  }
  rlBusy.value = true
  try {
    const out = await proposeRuleLearn({ min_count: 2 })
    ElMessage.success(`扫描 ${out.scanned_groups} 组，新建 ${out.created}`)
    await loadRuleLearn()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    rlBusy.value = false
  }
}

async function acceptRl(row: { id: number; proposal?: Record<string, unknown> }) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先填写操作令牌')
    return
  }
  let std_field: string | undefined
  const kind = row.proposal?.kind
  if (kind === 'map_alias') {
    std_field = window.prompt('确认映射到 std_field', String(row.proposal?.suggested_std_field || '')) || undefined
    if (!std_field) return
  }
  try {
    await confirmRuleLearn(row.id, { decision: 'accepted', std_field })
    ElMessage.success('已接受')
    await loadRuleLearn()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function rejectRl(id: number) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先填写操作令牌')
    return
  }
  try {
    await confirmRuleLearn(id, { decision: 'rejected' })
    ElMessage.success('已拒绝')
    await loadRuleLearn()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function loadMapPending() {
  mapPendingLoading.value = true
  try {
    const res = await listMapPending({ status: 'pending', limit: 100 })
    mapPending.value = res.items || []
    mapPendingTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    mapPendingLoading.value = false
  }
}

async function runEnqueue() {
  const headers = parseHeaders(headersText.value)
  if (!headers.length) {
    ElMessage.warning('请先输入表头')
    return
  }
  enqueueBusy.value = true
  try {
    const res = await enqueueMapHeaders({ headers, business_domain: 'default' })
    ElMessage.success(`已入队 ${res.enqueued} 条低置信/冲突项`)
    hint.value = res.hint || hint.value
    await loadMapPending()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    enqueueBusy.value = false
  }
}

async function decideMapPending(row: MapPendingItem, decision: 'accept' | 'amend' | 'ignore') {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  if (decision === 'amend' && !row.suggested_field) {
    ElMessage.warning('修正请先选择标准字段')
    return
  }
  try {
    await ElMessageBox.confirm(
      `${decision}「${row.header}」→ ${decision === 'ignore' ? '忽略' : row.suggested_field}？仅写规则字典。`,
      '映射确认门',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await confirmMapPending({
      pending_id: row.pending_id,
      decision,
      std_field: decision === 'ignore' ? 'ignore' : row.suggested_field || undefined,
    })
    notifyBrowse('已确认', 'fact_inventory')
    await Promise.all([loadMapPending(), loadRules()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function loadMasterPending() {
  masterPendingLoading.value = true
  try {
    const res = await listMasterPending({ status: 'pending', limit: 100 })
    masterPending.value = (res.items || []).map((i) => ({
      ...i,
      _mergeTo: i.candidates?.[0]?.material_id,
    }))
    masterPendingTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    masterPendingLoading.value = false
  }
}

async function runMasterPropose() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  masterProposeBusy.value = true
  try {
    const res = await proposeMasterPending(500)
    ElMessage.success(`扫描 ${res.scanned}，入队 ${res.enqueued}，刷新 ${res.refreshed}`)
    await loadMasterPending()
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
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  if (decision === 'merge' && !row._mergeTo && !(row.candidates || []).length) {
    ElMessage.warning('合并需要候选目标 material_id')
    return
  }
  const label = row.material_name || row.material_code || row.material_id || row.pending_id
  try {
    await ElMessageBox.confirm(
      `${decision}「${label}」？将经写入器写业务库。`,
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
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  }
}

async function runSuggest() {
  const headers = parseHeaders(headersText.value)
  if (!headers.length) {
    ElMessage.warning('请先输入表头')
    return
  }
  suggestBusy.value = true
  try {
    const res = await mapSuggest(headers)
    const mapping = res.mapping || {}
    const cands = res.candidates || {}
    rows.value = headers.map((h) => ({
      header: h,
      std_field: mapping[h] || 'ignore',
      candidates: (cands[h] || []).map((c) => ({
        std_field: c.std_field,
        score: Number(c.score) || 0,
      })),
    }))
    hint.value = res.hint || ''
    suggestMeta.value = {
      state: res.model_state,
      invoked: res.model_invoked,
      latency: res.latency_ms,
    }
    if (!res.ok) ElMessage.error(res.error || '建议失败')
    else ElMessage.success('已生成建议，请人工核对后确认')
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    suggestBusy.value = false
  }
}

async function runConfirm() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  if (!rows.value.length) return
  const mapping: Record<string, string> = {}
  for (const r of rows.value) {
    if (r.std_field && r.std_field !== 'ignore') mapping[r.header] = r.std_field
  }
  if (!Object.keys(mapping).length) {
    ElMessage.warning('没有可确认的映射（全为 ignore）')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将 ${Object.keys(mapping).length} 条映射写入规则字典？不会自动发布业务库。`,
      '映射确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  confirmBusy.value = true
  try {
    const res = await mapConfirm(mapping, note.value)
    ElMessage.success(`已保存 ${res.saved} 条（${res.actor}）`)
    await loadRules()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    confirmBusy.value = false
  }
}

async function loadRules() {
  rulesLoading.value = true
  try {
    const res = await listRuleDict(50, 0)
    rules.value = res.items
    rulesTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    rulesLoading.value = false
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
    })
    let items = res.items
    if (flowLevelFilter.value) {
      items = items.filter((x) => x.parse_level === flowLevelFilter.value)
    }
    flowItems.value = items
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

async function loadFlowExamples() {
  examplesLoading.value = true
  try {
    const res = await listFlowExamples(50, 0)
    flowExamples.value = res.items
    examplesTotal.value = res.total
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    examplesLoading.value = false
  }
}

async function decideOne(
  row: FlowPendingItem,
  decision: 'accept' | 'ignore',
  overwrite = false,
) {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
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
      ElMessage.warning('与已有 example 冲突，可切到 conflict 状态后「覆盖接受」')
    } else if (!res.ok) {
      ElMessage.error(res.code || '失败')
    } else {
      ElMessage.success(
        decision === 'accept' ? (overwrite ? '已覆盖接受' : '已接受') : '已忽略',
      )
    }
    await Promise.all([loadFlowPending(), loadFlowExamples(), loadFlowStats()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function batchAccept() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
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
    await Promise.all([loadFlowPending(), loadFlowExamples(), loadFlowStats()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function batchIgnore() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  const ids = selectedPending.value.map((x) => x.pending_id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`批量忽略 ${ids.length} 条？写入 L3 负例。`, '批量忽略', {
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
    await Promise.all([loadFlowPending(), loadFlowExamples(), loadFlowStats()])
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowBatchBusy.value = false
  }
}

async function runFlowSuggestSelected() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
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
    ElMessage.success(`大模型建议完成 ${ok}/${selectedPending.value.length}`)
    await loadFlowPending()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    flowSuggestBusy.value = false
  }
}

async function runFlowSuggestQueue() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  const limit = flowSuggestLimit.value
  try {
    await ElMessageBox.confirm(
      `对最多 ${limit} 条尚未建议的待确认项运行策略路由（快速模型→升级大模型）？仅写建议，不改业务库。`,
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
    ElMessage.success(`队列批处理完成（processed=${processed}）`)
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
    ElMessage.warning('请先在设置页填写操作令牌')
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
    ElMessage.success('已修正并回写 example')
    amendVisible.value = false
    await Promise.all([loadFlowPending(), loadFlowExamples(), loadFlowStats()])
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
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(
      '对「仅有库存、无流水」的物资写入 opening_qty=stock_qty（经 writer）。不处理已有流水的物资。确认？',
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
      ElMessage.info('无需更新（已无 inv_only 候选）')
      await loadReconcile()
      return
    }
    const res = await flowOpeningSeed(false)
    ElMessage.success(`已写入期初 ${res.updated ?? 0} 行`)
    await loadReconcile()
  } catch (e: unknown) {
    ElMessage.error(formatApiError(e))
  } finally {
    openingSeedBusy.value = false
  }
}

async function persistReconcile() {
  if (!localStorage.getItem('ops_token')) {
    ElMessage.warning('请先在设置页填写操作令牌')
    return
  }
  try {
    await ElMessageBox.confirm(
      '将删除并重建 meta.flow_reconcile_gap，供 FLOW_RECONCILE_GAP_CNT 读取。确认？',
      '重算并落库',
      { type: 'warning' },
    )
  } catch {
    return
  }
  reconcilePersistBusy.value = true
  try {
    const res = await flowReconcilePersist()
    applyReconcilePayload(res)
    notifyBrowse(`已落库 ${res.total} 条差异`, 'fact_stock_flow')
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
  a.download = `flow_reconcile_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  if (!localStorage.getItem('govern_guide_seen')) guideVisible.value = true
  try {
    const sf = await listStdFields()
    stdFields.value = sf.fields
  } catch {
    /* keep default */
  }
  await Promise.all([loadRules(), loadMapPending()])
})
</script>

<style scoped>
.govern { display: flex; flex-direction: column; gap: 16px; max-width: 1200px; }
.row-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
.hint { color: #909399; font-size: 13px; margin: 8px 0 0; }
.result-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cand { cursor: pointer; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
.pager { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 24px; font-weight: 600; margin-top: 4px; }
/* HG-3.4 勾稽差异行着色（scoped + :deep 作用于 el-table 行） */
:deep(.gap-inv_only) { background: #fef2f2; }
:deep(.gap-flow_only) { background: #fffbeb; }
:deep(.gap-mismatch) { background: #fff7ed; }
</style>
