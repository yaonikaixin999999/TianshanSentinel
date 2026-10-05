<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  Check,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  LocateFixed,
  MessageSquareText,
  RotateCcw,
  ShieldCheck,
  X,
} from 'lucide-vue-next'
import { fetchAnalysis, fetchReviews, reviewRegion } from '../api'
import CompareViewer from './CompareViewer.vue'

const props = defineProps({ focusedRegion: { type: Object, default: null } })
const emit = defineEmits(['updated'])

const queue = ref([])
const selected = ref(null)
const analysis = ref(null)
const statusFilter = ref('pending')
const eventType = ref('unclassified')
const reviewerNote = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref('')

const eventOptions = [
  { value: 'new_construction', label: '新增建设' },
  { value: 'demolition', label: '拆除清理' },
  { value: 'surface_change', label: '地表改造' },
  { value: 'uncertain_change', label: '其他变化' },
  { value: 'unclassified', label: '待判定' },
]
const statusCounts = computed(() => ({
  pending: queue.value.filter((item) => item.review_status === 'pending').length,
  approved: queue.value.filter((item) => item.review_status === 'approved').length,
  rejected: queue.value.filter((item) => item.review_status === 'rejected').length,
}))
const filteredQueue = computed(() => statusFilter.value === 'all' ? queue.value : queue.value.filter((item) => item.review_status === statusFilter.value))

async function loadQueue(preferred = null) {
  loading.value = true
  try {
    queue.value = (await fetchReviews('all')).items
    const target = preferred || props.focusedRegion
    const match = target && queue.value.find((item) => item.analysis_id === target.analysis_id && item.region_id === target.region_id)
    if (match) await selectRegion(match)
    else if (!selected.value && filteredQueue.value.length) await selectRegion(filteredQueue.value[0])
  } finally {
    loading.value = false
  }
}

async function selectRegion(region) {
  selected.value = region
  eventType.value = region.event_type || 'unclassified'
  reviewerNote.value = region.reviewer_note || ''
  analysis.value = await fetchAnalysis(region.analysis_id)
}

watch(statusFilter, async () => {
  if (!filteredQueue.value.some((item) => item.analysis_id === selected.value?.analysis_id && item.region_id === selected.value?.region_id)) {
    if (filteredQueue.value.length) await selectRegion(filteredQueue.value[0])
    else selected.value = null
  }
})
watch(() => props.focusedRegion, (region) => {
  if (region) loadQueue(region)
})

function eventLabel(value) {
  return eventOptions.find((option) => option.value === value)?.label || '待判定'
}

async function submitReview(reviewStatus) {
  if (!selected.value) return
  saving.value = true
  error.value = ''
  try {
    const label = eventType.value === 'unclassified' ? '待判定' : eventLabel(eventType.value)
    const updated = await reviewRegion(selected.value.analysis_id, selected.value.region_id, {
      event_type: eventType.value,
      event_label: label,
      review_status: reviewStatus,
      reviewer_note: reviewerNote.value,
    })
    emit('updated', updated)
    selected.value = null
    analysis.value = null
    await loadQueue()
  } catch (requestError) {
    error.value = requestError.response?.data?.detail || '复核结果保存失败。'
  } finally {
    saving.value = false
  }
}

onMounted(loadQueue)
</script>

<template>
  <section class="view-heading compact-heading">
    <div>
      <span class="eyebrow"><ClipboardCheck :size="14" /> HUMAN REVIEW</span>
      <h1>变化斑块复核中心</h1>
    </div>
    <div class="review-heading-stats">
      <span><i class="pending" />待复核 <strong>{{ statusCounts.pending }}</strong></span>
      <span><i class="approved" />已确认 <strong>{{ statusCounts.approved }}</strong></span>
      <span><i class="rejected" />已排除 <strong>{{ statusCounts.rejected }}</strong></span>
    </div>
  </section>

  <section class="review-layout">
    <aside class="review-queue surface-panel">
      <div class="review-tabs segmented">
        <button v-for="option in [{ value: 'pending', label: '待复核' }, { value: 'approved', label: '已确认' }, { value: 'rejected', label: '已排除' }, { value: 'all', label: '全部' }]" :key="option.value" type="button" :class="{ active: statusFilter === option.value }" @click="statusFilter = option.value">{{ option.label }}</button>
      </div>
      <div class="review-list">
        <button v-for="item in filteredQueue" :key="`${item.analysis_id}-${item.region_id}`" type="button" :class="{ active: selected?.analysis_id === item.analysis_id && selected?.region_id === item.region_id }" @click="selectRegion(item)">
          <span class="review-list-index">#{{ item.region_id }}</span>
          <span><strong>{{ item.event_label }}</strong><small>{{ item.project_name }}</small><em>{{ item.before_label }} → {{ item.after_label }}</em></span>
          <span class="confidence-value">{{ (item.mean_confidence * 100).toFixed(0) }}%</span>
        </button>
        <div v-if="!filteredQueue.length" class="panel-empty compact-empty"><CheckCircle2 :size="23" /><strong>当前队列为空</strong></div>
      </div>
    </aside>

    <div class="review-detail surface-panel">
      <template v-if="selected && analysis">
        <div class="review-detail-header">
          <div class="result-title"><span class="result-check"><LocateFixed :size="18" /></span><div><span>任务 {{ analysis.id.slice(0, 8) }} · 斑块 #{{ selected.region_id }}</span><h2>{{ selected.project_name }}</h2></div></div>
          <span class="table-risk" :class="selected.risk_level">{{ selected.risk_level === 'high' ? '高风险' : selected.risk_level === 'medium' ? '中风险' : '低风险' }}</span>
        </div>
        <CompareViewer :before-url="analysis.before_url" :after-url="analysis.after_url" :overlay-url="analysis.overlay_url" />
        <div class="review-evidence-strip">
          <div><small>斑块范围</small><strong>{{ selected.width }} × {{ selected.height }} px</strong></div>
          <div><small>像素面积</small><strong>{{ selected.area_pixels.toLocaleString() }}</strong></div>
          <div><small>模型置信度</small><strong>{{ (selected.mean_confidence * 100).toFixed(1) }}%</strong></div>
          <div><small>规则建议置信度</small><strong>{{ ((selected.event_confidence || 0) * 100).toFixed(1) }}%</strong></div>
        </div>
        <div class="review-form">
          <div class="review-form-heading"><ShieldCheck :size="17" /><div><strong>人工复核意见</strong><span>AUDIT DECISION</span></div></div>
          <label><span>事件类型</span><select v-model="eventType" class="select-control"><option v-for="option in eventOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          <label><span>复核备注</span><textarea v-model="reviewerNote" rows="3" maxlength="300" placeholder="记录判定依据或现场核查信息" /></label>
          <p v-if="error" class="error-message">{{ error }}</p>
          <div class="review-actions">
            <button class="reject-button" type="button" :disabled="saving" @click="submitReview('rejected')"><X :size="16" />排除误检</button>
            <button class="secondary-button" type="button" :disabled="saving" @click="eventType = selected.event_type; reviewerNote = selected.reviewer_note"><RotateCcw :size="15" />重置</button>
            <button class="approve-button" type="button" :disabled="saving" @click="submitReview('approved')"><Check :size="16" />确认变化</button>
          </div>
        </div>
      </template>
      <div v-else class="panel-empty review-empty"><ClipboardCheck :size="30" /><strong>选择待复核斑块</strong><span>REVIEW QUEUE</span></div>
    </div>
  </section>
</template>
