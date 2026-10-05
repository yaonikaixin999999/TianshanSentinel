<script setup>
import { computed, ref, watch } from 'vue'
import {
  Activity,
  Archive,
  BellRing,
  CalendarRange,
  Download,
  FolderKanban,
  MapPin,
  Plus,
  Save,
  X,
} from 'lucide-vue-next'
import { createProject, fetchTimeline, projectTimelineExportUrl, updateProject } from '../api'
import TrendChart from './TrendChart.vue'

const props = defineProps({
  projects: { type: Array, default: () => [] },
  selectedProjectId: { type: String, default: '' },
})
const emit = defineEmits(['refresh', 'analyze', 'selected'])

const selectedId = ref('')
const timeline = ref({ items: [] })
const loading = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const error = ref('')
const form = ref({ name: '', description: '', area_name: '', center_lat: null, center_lon: null, alert_threshold: 0.12 })
const thresholdDraft = ref(12)

const selectedProject = computed(() => props.projects.find((project) => project.id === selectedId.value))
const riskLabel = { high: '高风险', medium: '中风险', low: '低风险' }

async function selectProject(projectId) {
  selectedId.value = projectId
  emit('selected', projectId)
  loading.value = true
  try {
    timeline.value = await fetchTimeline(projectId)
    thresholdDraft.value = Math.round((timeline.value.project?.alert_threshold || 0.12) * 100)
  } finally {
    loading.value = false
  }
}

watch(() => [props.projects, props.selectedProjectId], ([projects, incoming]) => {
  const target = incoming || selectedId.value || projects[0]?.id
  if (target && target !== selectedId.value) selectProject(target)
  else if (target && !timeline.value.project) selectProject(target)
}, { immediate: true, deep: true })

async function submitProject() {
  if (!form.value.name.trim()) return
  saving.value = true
  error.value = ''
  try {
    const project = await createProject({
      ...form.value,
      center_lat: form.value.center_lat === '' ? null : form.value.center_lat,
      center_lon: form.value.center_lon === '' ? null : form.value.center_lon,
    })
    modalOpen.value = false
    form.value = { name: '', description: '', area_name: '', center_lat: null, center_lon: null, alert_threshold: 0.12 }
    await emit('refresh')
    await selectProject(project.id)
  } catch (requestError) {
    error.value = requestError.response?.data?.detail?.[0]?.msg || '项目创建失败。'
  } finally {
    saving.value = false
  }
}

async function saveThreshold() {
  if (!selectedProject.value) return
  saving.value = true
  try {
    await updateProject(selectedProject.value.id, { alert_threshold: thresholdDraft.value / 100 })
    await emit('refresh')
    await selectProject(selectedProject.value.id)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="view-heading compact-heading">
    <div>
      <span class="eyebrow"><FolderKanban :size="14" /> PROJECT PORTFOLIO</span>
      <h1>监测项目管理</h1>
    </div>
    <button class="primary-button header-action" type="button" @click="modalOpen = true"><Plus :size="17" />创建监测项目</button>
  </section>

  <section class="project-management-layout">
    <div class="project-list-panel surface-panel">
      <div class="panel-header">
        <div class="section-title"><span class="section-icon"><FolderKanban :size="18" /></span><div><h2>项目目录</h2><span>{{ projects.length }} PROJECTS</span></div></div>
      </div>
      <div class="project-list">
        <button v-for="project in projects" :key="project.id" type="button" :class="{ active: project.id === selectedId }" @click="selectProject(project.id)">
          <span class="project-monogram">{{ project.name.slice(0, 1) }}</span>
          <span><strong>{{ project.name }}</strong><small><MapPin :size="11" />{{ project.area_name }}</small></span>
          <i :class="{ alerting: project.alerting }" />
        </button>
      </div>
    </div>

    <div v-if="selectedProject" class="project-detail-panel surface-panel">
      <div class="project-detail-header">
        <div>
          <span class="eyebrow">PROJECT {{ selectedProject.id.slice(0, 8) }}</span>
          <h2>{{ selectedProject.name }}</h2>
          <p>{{ selectedProject.description || '暂无项目描述' }}</p>
        </div>
        <div class="project-detail-actions">
          <a :href="projectTimelineExportUrl(selectedProject.id)" class="secondary-button"><Download :size="15" />导出时间轴</a>
          <button class="primary-button" type="button" @click="emit('analyze', selectedProject.id)"><Activity :size="15" />新建研判</button>
        </div>
      </div>

      <div class="project-kpis">
        <div><small>分析任务</small><strong>{{ selectedProject.analysis_count }}</strong></div>
        <div><small>变化斑块</small><strong>{{ selectedProject.region_count }}</strong></div>
        <div><small>最新变化率</small><strong :class="{ danger: selectedProject.alerting }">{{ (selectedProject.latest_change_ratio * 100).toFixed(2) }}%</strong></div>
        <div><small>待复核</small><strong>{{ selectedProject.pending_reviews }}</strong></div>
      </div>

      <div class="project-detail-grid">
        <div class="project-trend-block">
          <div class="subpanel-title"><CalendarRange :size="16" /><strong>多时相变化时间轴</strong><span>{{ timeline.items?.length || 0 }} 个检测节点</span></div>
          <TrendChart :items="timeline.items || []" :threshold="selectedProject.alert_threshold" />
        </div>
        <div class="project-settings-block">
          <div class="subpanel-title"><BellRing :size="16" /><strong>变化预警阈值</strong></div>
          <div class="threshold-value"><strong>{{ thresholdDraft }}%</strong><span :class="{ alerting: selectedProject.alerting }">{{ selectedProject.alerting ? '已触发预警' : '监测正常' }}</span></div>
          <input v-model.number="thresholdDraft" type="range" min="1" max="50" step="1" aria-label="项目预警阈值" />
          <div class="threshold-scale"><span>1%</span><span>50%</span></div>
          <button class="secondary-button full-button" type="button" :disabled="saving" @click="saveThreshold"><Save :size="15" />保存阈值</button>
          <div class="location-summary"><MapPin :size="15" /><span><small>监测区域</small><strong>{{ selectedProject.area_name }}</strong><em v-if="selectedProject.center_lat != null">{{ selectedProject.center_lat.toFixed(4) }}, {{ selectedProject.center_lon.toFixed(4) }}</em></span></div>
        </div>
      </div>

      <div class="timeline-table">
        <div class="subpanel-title"><CalendarRange :size="16" /><strong>分析节点</strong></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>任务</th><th>时相区间</th><th>变化率</th><th>斑块</th><th>风险</th><th>复核</th></tr></thead>
            <tbody>
              <tr v-for="item in [...(timeline.items || [])].reverse()" :key="item.id">
                <td><code>{{ item.id.slice(0, 8) }}</code></td><td>{{ item.before_label }} → {{ item.after_label }}</td>
                <td><strong class="ratio-value">{{ (item.change_ratio * 100).toFixed(2) }}%</strong></td><td>{{ item.region_count }}</td>
                <td><span class="table-risk" :class="item.overall_risk">{{ riskLabel[item.overall_risk] }}</span></td>
                <td>{{ item.reviewed_regions }}/{{ item.region_count }}</td>
              </tr>
              <tr v-if="!timeline.items?.length"><td colspan="6" class="empty-row">暂无时间轴节点</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <div v-if="modalOpen" class="modal-backdrop" @click.self="modalOpen = false">
    <form class="modal-panel" @submit.prevent="submitProject">
      <div class="modal-header"><div><span>NEW MONITORING PROJECT</span><h2>创建监测项目</h2></div><button class="icon-button" type="button" aria-label="关闭" @click="modalOpen = false"><X :size="18" /></button></div>
      <div class="form-grid">
        <label class="wide"><span>项目名称</span><input v-model="form.name" required maxlength="80" placeholder="例如：新疆大学校园建设监测" /></label>
        <label class="wide"><span>监测区域</span><input v-model="form.area_name" maxlength="100" placeholder="区域或地块名称" /></label>
        <label><span>中心纬度</span><input v-model="form.center_lat" type="number" min="-90" max="90" step="0.0001" placeholder="43.8256" /></label>
        <label><span>中心经度</span><input v-model="form.center_lon" type="number" min="-180" max="180" step="0.0001" placeholder="87.6168" /></label>
        <label class="wide"><span>项目描述</span><textarea v-model="form.description" maxlength="300" rows="3" placeholder="监测目标与业务范围" /></label>
        <label class="wide"><span>预警阈值 {{ Math.round(form.alert_threshold * 100) }}%</span><input v-model.number="form.alert_threshold" type="range" min="0.01" max="0.5" step="0.01" /></label>
      </div>
      <p v-if="error" class="error-message">{{ error }}</p>
      <div class="modal-actions"><button class="secondary-button" type="button" @click="modalOpen = false">取消</button><button class="primary-button" type="submit" :disabled="saving"><Plus :size="16" />{{ saving ? '创建中' : '创建项目' }}</button></div>
    </form>
  </div>
</template>
