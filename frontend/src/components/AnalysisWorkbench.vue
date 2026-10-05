<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  Activity,
  CalendarRange,
  CheckCircle2,
  Database,
  Download,
  FileJson,
  Files,
  FileText,
  Layers3,
  LoaderCircle,
  Play,
  RotateCcw,
  ScanSearch,
  UploadCloud,
} from 'lucide-vue-next'
import { analysisExportUrl, analyzePair } from '../api'
import CompareViewer from './CompareViewer.vue'
import ImagePairInput from './ImagePairInput.vue'

const props = defineProps({
  projects: { type: Array, default: () => [] },
  focusedAnalysis: { type: Object, default: null },
  selectedProjectId: { type: String, default: '' },
})
const emit = defineEmits(['completed', 'open-review'])

const mode = ref('single')
const projectId = ref('')
const before = ref(null)
const after = ref(null)
const beforeLabel = ref('T1')
const afterLabel = ref('T2')
const beforePreview = ref('')
const afterPreview = ref('')
const result = ref(null)
const busy = ref(false)
const error = ref('')
const timelineFiles = ref([])
const batchProgress = ref(0)
const batchResults = ref([])

const riskLabel = { high: '高风险', medium: '中风险', low: '低风险' }
const selectedProject = computed(() => props.projects.find((project) => project.id === projectId.value))
const taskState = computed(() => {
  if (busy.value) return mode.value === 'batch' ? `批量研判 ${batchProgress.value}%` : '模型推理中'
  if (mode.value === 'batch') return timelineFiles.value.length >= 2 ? `${timelineFiles.value.length} 期影像已就绪` : '等待多时相影像'
  if (before.value && after.value) return '双时相影像已就绪'
  return '等待影像'
})

function syncPreview(file, target) {
  if (target.value) URL.revokeObjectURL(target.value)
  target.value = file ? URL.createObjectURL(file) : ''
}
watch(before, (file) => syncPreview(file, beforePreview))
watch(after, (file) => syncPreview(file, afterPreview))
watch(() => props.projects, (projects) => {
  if (props.selectedProjectId && projects.some((project) => project.id === props.selectedProjectId)) projectId.value = props.selectedProjectId
  else if (!projectId.value && projects.length) projectId.value = projects[0].id
}, { immediate: true })
watch(() => props.selectedProjectId, (value) => {
  if (value) projectId.value = value
})
watch(() => props.focusedAnalysis, (analysis) => {
  if (analysis) {
    result.value = analysis
    projectId.value = analysis.project_id || projectId.value
    beforeLabel.value = analysis.before_label || 'T1'
    afterLabel.value = analysis.after_label || 'T2'
  }
}, { immediate: true })

async function loadDemo() {
  const files = await Promise.all(['/demo/before.png', '/demo/after.png'].map(async (url) => {
    const blob = await (await fetch(url)).blob()
    return new File([blob], url.includes('before') ? 'demo_before.png' : 'demo_after.png', { type: 'image/png' })
  }))
  ;[before.value, after.value] = files
  beforeLabel.value = '示例前时相'
  afterLabel.value = '示例后时相'
  result.value = null
  error.value = ''
}

async function runAnalysis() {
  if (!before.value || !after.value) return
  busy.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await analyzePair(before.value, after.value, {
      projectId: projectId.value,
      beforeLabel: beforeLabel.value,
      afterLabel: afterLabel.value,
    })
    emit('completed', result.value)
  } catch (requestError) {
    error.value = requestError.response?.data?.detail || '分析失败，请检查服务状态与影像格式。'
  } finally {
    busy.value = false
  }
}

function chooseTimeline(event) {
  timelineFiles.value = [...event.target.files].sort((left, right) => left.name.localeCompare(right.name, 'zh-CN', { numeric: true }))
  batchResults.value = []
  batchProgress.value = 0
  result.value = null
  error.value = ''
  event.target.value = ''
}

function timeLabel(file, fallback) {
  return file?.name?.replace(/\.[^.]+$/, '').slice(0, 40) || fallback
}

async function runTimeline() {
  if (timelineFiles.value.length < 2) return
  busy.value = true
  error.value = ''
  batchResults.value = []
  try {
    for (let index = 0; index < timelineFiles.value.length - 1; index += 1) {
      const current = timelineFiles.value[index]
      const next = timelineFiles.value[index + 1]
      const analysis = await analyzePair(current, next, {
        projectId: projectId.value,
        beforeLabel: timeLabel(current, `T${index + 1}`),
        afterLabel: timeLabel(next, `T${index + 2}`),
      })
      batchResults.value.push(analysis)
      result.value = analysis
      batchProgress.value = Math.round(((index + 1) / (timelineFiles.value.length - 1)) * 100)
      emit('completed', analysis)
    }
  } catch (requestError) {
    error.value = requestError.response?.data?.detail || `批量任务在第 ${batchResults.value.length + 1} 组失败。`
  } finally {
    busy.value = false
  }
}

function reset() {
  before.value = null
  after.value = null
  timelineFiles.value = []
  batchResults.value = []
  batchProgress.value = 0
  result.value = null
  error.value = ''
}

onBeforeUnmount(() => {
  if (beforePreview.value) URL.revokeObjectURL(beforePreview.value)
  if (afterPreview.value) URL.revokeObjectURL(afterPreview.value)
})
</script>

<template>
  <section class="view-heading compact-heading">
    <div>
      <span class="eyebrow"><ScanSearch :size="14" /> CHANGE ANALYSIS</span>
      <h1>智能变化研判</h1>
    </div>
    <div class="heading-context">
      <span>当前项目</span><strong>{{ selectedProject?.name || '未选择项目' }}</strong>
    </div>
  </section>

  <section class="workspace-band analysis-workspace">
    <div class="workspace-header">
      <div class="workspace-title">
        <span class="section-icon"><Layers3 :size="18" /></span>
        <div><h2>影像任务配置</h2><span>ANALYSIS WORKSPACE</span></div>
      </div>
      <div class="workspace-mode segmented">
        <button type="button" :class="{ active: mode === 'single' }" @click="mode = 'single'"><Files :size="14" />双时相</button>
        <button type="button" :class="{ active: mode === 'batch' }" @click="mode = 'batch'"><CalendarRange :size="14" />多时相</button>
      </div>
      <div class="workspace-status" :class="{ ready: (before && after) || timelineFiles.length >= 2, running: busy }">
        <span class="status-dot" />{{ taskState }}
      </div>
    </div>

    <div class="workspace-grid">
      <aside class="control-panel">
        <div class="field-block">
          <label>归属监测项目</label>
          <select v-model="projectId" class="select-control">
            <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
          </select>
        </div>

        <template v-if="mode === 'single'">
          <div class="phase-label-row">
            <label><span>T1</span><input v-model="beforeLabel" maxlength="40" aria-label="前时相标签" /></label>
            <label><span>T2</span><input v-model="afterLabel" maxlength="40" aria-label="后时相标签" /></label>
          </div>
          <div class="input-stack">
            <ImagePairInput phase="T1" label="前时相影像" :file="before" :preview="beforePreview" @update:file="before = $event" />
            <span class="phase-link"><span /><span /><span /></span>
            <ImagePairInput phase="T2" label="后时相影像" :file="after" :preview="afterPreview" @update:file="after = $event" />
          </div>
        </template>

        <template v-else>
          <label class="timeline-drop-zone">
            <span class="upload-symbol"><UploadCloud :size="22" /></span>
            <strong>选择连续时相影像</strong>
            <small>2-8 期 · PNG / JPG / TIFF</small>
            <input type="file" multiple accept="image/png,image/jpeg,image/tiff,.tif,.tiff" @change="chooseTimeline" />
          </label>
          <div class="timeline-file-list">
            <div v-for="(file, index) in timelineFiles" :key="`${file.name}-${index}`">
              <span class="timeline-index">T{{ index + 1 }}</span>
              <span><strong>{{ timeLabel(file, `T${index + 1}`) }}</strong><small>{{ (file.size / 1024 / 1024).toFixed(1) }} MB</small></span>
              <i v-if="index < timelineFiles.length - 1" />
            </div>
            <div v-if="!timelineFiles.length" class="timeline-empty">尚未载入时相序列</div>
          </div>
          <div v-if="busy || batchResults.length" class="batch-progress">
            <span><i :style="{ width: `${batchProgress}%` }" /></span>
            <small>{{ batchResults.length }} / {{ Math.max(timelineFiles.length - 1, 0) }} 组完成</small>
          </div>
        </template>

        <p v-if="error" class="error-message">{{ error }}</p>
        <div class="action-row">
          <button v-if="mode === 'single'" class="secondary-button" type="button" @click="loadDemo"><Database :size="17" />载入示例</button>
          <button class="icon-button bordered" type="button" title="重置任务" aria-label="重置任务" @click="reset"><RotateCcw :size="17" /></button>
          <button v-if="mode === 'single'" class="primary-button" type="button" :disabled="!before || !after || busy" @click="runAnalysis">
            <LoaderCircle v-if="busy" class="spin" :size="17" /><Play v-else :size="17" fill="currentColor" />{{ busy ? '模型研判中' : '开始智能研判' }}
          </button>
          <button v-else class="primary-button" type="button" :disabled="timelineFiles.length < 2 || busy" @click="runTimeline">
            <LoaderCircle v-if="busy" class="spin" :size="17" /><Play v-else :size="17" fill="currentColor" />{{ busy ? `批量分析 ${batchProgress}%` : `分析 ${Math.max(timelineFiles.length - 1, 0)} 组时相` }}
          </button>
        </div>
      </aside>

      <div class="result-panel">
        <template v-if="result">
          <div class="result-header">
            <div class="result-title">
              <span class="result-check"><CheckCircle2 :size="18" /></span>
              <div><span>任务 {{ result.id.slice(0, 8) }} · {{ result.before_label }} → {{ result.after_label }}</span><h2>变化检测结果</h2></div>
            </div>
            <div class="result-actions">
              <a :href="analysisExportUrl(result.id, 'pdf')" class="icon-button bordered" title="下载 PDF 报告"><Download :size="15" /></a>
              <span class="risk-badge" :class="result.overall_risk">{{ riskLabel[result.overall_risk] }}</span>
            </div>
          </div>
          <CompareViewer :before-url="result.before_url" :after-url="result.after_url" :overlay-url="result.overlay_url" />
          <div class="result-metrics">
            <div class="primary-metric"><span>变化占比</span><strong>{{ (result.change_ratio * 100).toFixed(2) }}%</strong></div>
            <div><span>平均置信度</span><strong>{{ (result.mean_confidence * 100).toFixed(1) }}%</strong></div>
            <div><span>平均不确定性</span><strong>{{ (result.mean_uncertainty * 100).toFixed(1) }}%</strong></div>
            <div><span>有效变化斑块</span><strong>{{ result.region_count }}</strong></div>
          </div>
          <div class="result-lower">
            <div class="narrative-inline"><Activity :size="17" /><p>{{ result.narrative }}</p></div>
            <div class="event-tags">
              <button v-for="region in result.regions.slice(0, 5)" :key="region.region_id" type="button" @click="emit('open-review', result, region)">
                <span>#{{ region.region_id }}</span><strong>{{ region.event_label || '待判定' }}</strong><small>{{ region.review_status === 'pending' ? '待复核' : '已处理' }}</small>
              </button>
            </div>
            <div class="quick-exports">
              <span>成果导出</span>
              <a :href="analysisExportUrl(result.id, 'docx')"><FileText :size="14" />Word 报告</a>
              <a :href="analysisExportUrl(result.id, 'pdf')"><Download :size="14" />PDF 报告</a>
              <a :href="analysisExportUrl(result.id, 'geojson')"><FileJson :size="14" />GeoJSON</a>
            </div>
          </div>
        </template>

        <div v-else class="empty-result">
          <div class="empty-visual">
            <div><img src="/demo/before.png" alt="遥感前时相示例" /><span>T1</span></div>
            <div><img src="/demo/after.png" alt="遥感后时相示例" /><span>T2</span></div>
            <span class="scan-line" />
          </div>
          <span class="empty-icon"><ScanSearch :size="25" /></span>
          <h2>{{ taskState }}</h2>
          <span>NO ANALYSIS DATA</span>
        </div>
      </div>
    </div>
  </section>
</template>
