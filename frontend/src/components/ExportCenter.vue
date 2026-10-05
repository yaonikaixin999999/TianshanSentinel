<script setup>
import { computed, ref, watch } from 'vue'
import {
  CheckCircle2,
  ChevronRight,
  Download,
  FileJson,
  FileSpreadsheet,
  FileText,
  PackageCheck,
  ShieldCheck,
} from 'lucide-vue-next'
import { analysisExportUrl, projectTimelineExportUrl } from '../api'

const props = defineProps({
  history: { type: Array, default: () => [] },
  projects: { type: Array, default: () => [] },
})
const selectedId = ref('')
const projectId = ref('')
const selected = computed(() => props.history.find((item) => item.id === selectedId.value) || props.history[0])
const projectMap = computed(() => Object.fromEntries(props.projects.map((project) => [project.id, project])))
const selectedProject = computed(() => projectMap.value[selected.value?.project_id])
const riskLabel = { high: '高风险', medium: '中风险', low: '低风险' }

watch(() => props.history, (history) => {
  if (!selectedId.value && history.length) selectedId.value = history[0].id
}, { immediate: true })
watch(() => props.projects, (projects) => {
  if (!projectId.value && projects.length) projectId.value = projects[0].id
}, { immediate: true })
</script>

<template>
  <section class="view-heading compact-heading">
    <div>
      <span class="eyebrow"><PackageCheck :size="14" /> DELIVERABLE CENTER</span>
      <h1>成果导出中心</h1>
    </div>
    <div class="project-export-control">
      <select v-model="projectId" class="select-control"><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select>
      <a v-if="projectId" :href="projectTimelineExportUrl(projectId)" class="secondary-button"><FileSpreadsheet :size="15" />项目时间轴 CSV</a>
    </div>
  </section>

  <section class="export-layout">
    <aside class="export-list surface-panel">
      <div class="panel-header"><div class="section-title"><span class="section-icon"><PackageCheck :size="18" /></span><div><h2>分析成果</h2><span>{{ history.length }} DELIVERABLES</span></div></div></div>
      <div class="export-analysis-list">
        <button v-for="item in history" :key="item.id" type="button" :class="{ active: selected?.id === item.id }" @click="selectedId = item.id">
          <span><strong>{{ projectMap[item.project_id]?.name || '历史检测任务' }}</strong><small>{{ item.before_label }} → {{ item.after_label }}</small><em>{{ new Date(item.created_at).toLocaleDateString('zh-CN') }}</em></span>
          <span><i class="table-risk" :class="item.overall_risk">{{ riskLabel[item.overall_risk] }}</i><ChevronRight :size="15" /></span>
        </button>
      </div>
    </aside>

    <div v-if="selected" class="export-detail surface-panel">
      <div class="export-preview">
        <img :src="selected.overlay_url" alt="变化叠加成果预览" />
        <div class="export-preview-overlay">
          <span>REPORT PREVIEW</span><strong>{{ selectedProject?.name || '历史检测任务' }}</strong><small>任务 {{ selected.id.slice(0, 8) }}</small>
        </div>
      </div>
      <div class="export-summary">
        <div class="export-summary-header">
          <div><span class="eyebrow">CHANGE AUDIT PACKAGE</span><h2>变化检测成果包</h2></div>
          <span class="risk-badge" :class="selected.overall_risk"><ShieldCheck :size="14" />{{ riskLabel[selected.overall_risk] }}</span>
        </div>
        <p>{{ selected.narrative }}</p>
        <div class="export-facts">
          <div><small>变化占比</small><strong>{{ (selected.change_ratio * 100).toFixed(2) }}%</strong></div>
          <div><small>变化斑块</small><strong>{{ selected.region_count }}</strong></div>
          <div><small>复核进度</small><strong>{{ (selected.review_progress * 100).toFixed(0) }}%</strong></div>
        </div>
        <div class="export-options">
          <a :href="analysisExportUrl(selected.id, 'docx')">
            <span class="export-file-icon word"><FileText :size="21" /></span>
            <span><strong>Word 审计报告</strong><small>DOCX · 图文报告</small></span><Download :size="17" />
          </a>
          <a :href="analysisExportUrl(selected.id, 'pdf')">
            <span class="export-file-icon pdf"><FileText :size="21" /></span>
            <span><strong>PDF 定版报告</strong><small>PDF · 归档文件</small></span><Download :size="17" />
          </a>
          <a :href="analysisExportUrl(selected.id, 'geojson')">
            <span class="export-file-icon geo"><FileJson :size="21" /></span>
            <span><strong>变化斑块 GeoJSON</strong><small>GEOJSON · 像素坐标</small></span><Download :size="17" />
          </a>
        </div>
        <div class="export-checks">
          <span><CheckCircle2 :size="14" />影像证据已嵌入</span>
          <span><CheckCircle2 :size="14" />模型参数已记录</span>
          <span><CheckCircle2 :size="14" />复核状态已同步</span>
        </div>
      </div>
    </div>
    <div v-else class="export-detail surface-panel panel-empty review-empty"><PackageCheck :size="30" /><strong>暂无可导出成果</strong></div>
  </section>
</template>
