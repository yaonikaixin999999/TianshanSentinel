<script setup>
import { computed } from 'vue'
import {
  Activity,
  ArrowUpRight,
  BellRing,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Cpu,
  FolderKanban,
  Layers3,
  Radar,
  ShieldAlert,
} from 'lucide-vue-next'
import TrendChart from './TrendChart.vue'

const props = defineProps({
  statistics: { type: Object, required: true },
  projects: { type: Array, default: () => [] },
  history: { type: Array, default: () => [] },
  health: { type: Object, required: true },
})
const emit = defineEmits(['navigate', 'open-analysis', 'select-project'])

const alertProjects = computed(() => props.projects.filter((project) => project.alerting))
const recentHistory = computed(() => props.history.slice(0, 6))
const trendItems = computed(() => [...props.history].slice(0, 12).reverse())
const riskLabel = { high: '高风险', medium: '中风险', low: '低风险' }
</script>

<template>
  <section class="view-heading compact-heading">
    <div>
      <span class="eyebrow"><Radar :size="14" /> MONITORING OVERVIEW</span>
      <h1>遥感监测总览</h1>
    </div>
    <button class="primary-button header-action" type="button" @click="emit('navigate', 'analysis')">
      <Activity :size="17" />新建研判任务
    </button>
  </section>

  <section class="overview-metrics">
    <div class="overview-metric">
      <span class="metric-icon blue"><FolderKanban :size="18" /></span>
      <span><small>运行项目</small><strong>{{ statistics.active_projects || projects.length }}</strong><em>ACTIVE PROJECTS</em></span>
    </div>
    <div class="overview-metric">
      <span class="metric-icon cyan"><Layers3 :size="18" /></span>
      <span><small>累计研判</small><strong>{{ statistics.total_analyses }}</strong><em>ANALYSES</em></span>
    </div>
    <div class="overview-metric">
      <span class="metric-icon amber"><ClipboardCheck :size="18" /></span>
      <span><small>待复核斑块</small><strong>{{ statistics.pending_reviews || 0 }}</strong><em>PENDING REVIEW</em></span>
    </div>
    <div class="overview-metric">
      <span class="metric-icon red"><BellRing :size="18" /></span>
      <span><small>项目预警</small><strong>{{ alertProjects.length }}</strong><em>ACTIVE ALERTS</em></span>
    </div>
  </section>

  <section class="dashboard-grid">
    <div class="surface-panel trend-panel">
      <div class="panel-header">
        <div class="section-title">
          <span class="section-icon"><Activity :size="18" /></span>
          <div><h2>近期变化趋势</h2><span>CHANGE RATE / REGION COUNT</span></div>
        </div>
        <span class="panel-meta">最近 {{ trendItems.length }} 次分析</span>
      </div>
      <TrendChart :items="trendItems" />
    </div>

    <div class="surface-panel alert-panel">
      <div class="panel-header">
        <div class="section-title">
          <span class="section-icon warning"><ShieldAlert :size="18" /></span>
          <div><h2>监测预警</h2><span>THRESHOLD ALERTS</span></div>
        </div>
        <span class="alert-count">{{ alertProjects.length }}</span>
      </div>
      <div v-if="alertProjects.length" class="alert-list">
        <button v-for="project in alertProjects.slice(0, 4)" :key="project.id" type="button" @click="emit('select-project', project.id)">
          <span class="alert-symbol"><BellRing :size="15" /></span>
          <span><strong>{{ project.name }}</strong><small>{{ project.area_name }} · 最新变化 {{ (project.latest_change_ratio * 100).toFixed(1) }}%</small></span>
          <ArrowUpRight :size="15" />
        </button>
      </div>
      <div v-else class="panel-empty compact-empty">
        <CheckCircle2 :size="24" /><strong>当前无阈值预警</strong><span>所有项目均在设定范围内</span>
      </div>
      <div class="engine-summary">
        <span><Cpu :size="15" /></span>
        <div><small>当前推理引擎</small><strong>{{ health.engine }}</strong></div>
        <i :class="health.status" />
      </div>
    </div>
  </section>

  <section class="surface-panel project-overview">
    <div class="panel-header">
      <div class="section-title">
        <span class="section-icon"><FolderKanban :size="18" /></span>
        <div><h2>监测项目</h2><span>PROJECT PORTFOLIO</span></div>
      </div>
      <button class="text-button" type="button" @click="emit('navigate', 'projects')">管理全部 <ArrowUpRight :size="14" /></button>
    </div>
    <div class="project-row">
      <button v-for="project in projects.slice(0, 4)" :key="project.id" class="project-summary" type="button" @click="emit('select-project', project.id)">
        <span class="project-monogram">{{ project.name.slice(0, 1) }}</span>
        <span class="project-summary-copy">
          <strong>{{ project.name }}</strong><small>{{ project.area_name }}</small>
          <span><i>{{ project.analysis_count }} 次分析</i><i>{{ project.region_count }} 个斑块</i></span>
        </span>
        <span class="project-change" :class="{ alerting: project.alerting }">{{ (project.latest_change_ratio * 100).toFixed(1) }}%</span>
      </button>
    </div>
  </section>

  <section class="surface-panel recent-panel">
    <div class="panel-header">
      <div class="section-title">
        <span class="section-icon"><Clock3 :size="18" /></span>
        <div><h2>最近分析</h2><span>RECENT ANALYSES</span></div>
      </div>
      <span class="panel-meta">实时同步</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>任务编号</th><th>时相</th><th>分析时间</th><th>变化率</th><th>变化斑块</th><th>复核进度</th><th>风险</th><th /></tr></thead>
        <tbody>
          <tr v-for="item in recentHistory" :key="item.id" @click="emit('open-analysis', item)">
            <td><code>{{ item.id.slice(0, 8) }}</code></td>
            <td>{{ item.before_label }} → {{ item.after_label }}</td>
            <td>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</td>
            <td><strong class="ratio-value">{{ (item.change_ratio * 100).toFixed(2) }}%</strong></td>
            <td>{{ item.region_count }}</td>
            <td><span class="review-progress"><i :style="{ width: `${item.review_progress * 100}%` }" /></span>{{ (item.review_progress * 100).toFixed(0) }}%</td>
            <td><span class="table-risk" :class="item.overall_risk">{{ riskLabel[item.overall_risk] }}</span></td>
            <td><ArrowUpRight :size="14" /></td>
          </tr>
          <tr v-if="!recentHistory.length"><td colspan="8" class="empty-row">暂无分析记录</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
