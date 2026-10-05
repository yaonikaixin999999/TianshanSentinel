<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import {
  Bell,
  ClipboardCheck,
  FolderKanban,
  LayoutDashboard,
  PackageCheck,
  Plus,
  Satellite,
  ScanSearch,
} from 'lucide-vue-next'
import { fetchHealth, fetchHistory, fetchProjects, fetchStatistics } from './api'

const OverviewDashboard = defineAsyncComponent(() => import('./components/OverviewDashboard.vue'))
const AnalysisWorkbench = defineAsyncComponent(() => import('./components/AnalysisWorkbench.vue'))
const ProjectPortfolio = defineAsyncComponent(() => import('./components/ProjectPortfolio.vue'))
const ReviewCenter = defineAsyncComponent(() => import('./components/ReviewCenter.vue'))
const ExportCenter = defineAsyncComponent(() => import('./components/ExportCenter.vue'))

const activeView = ref('overview')
const health = ref({ status: 'checking', engine: '引擎连接中' })
const statistics = ref({
  total_analyses: 0,
  active_projects: 0,
  total_regions: 0,
  pending_reviews: 0,
  average_change_ratio: 0,
})
const history = ref([])
const projects = ref([])
const focusedAnalysis = ref(null)
const focusedRegion = ref(null)
const selectedProjectId = ref('')
const loading = ref(true)

const navigation = [
  { id: 'overview', label: '监测总览', caption: 'OVERVIEW', icon: LayoutDashboard },
  { id: 'analysis', label: '智能研判', caption: 'ANALYSIS', icon: ScanSearch },
  { id: 'projects', label: '监测项目', caption: 'PROJECTS', icon: FolderKanban },
  { id: 'review', label: '斑块复核', caption: 'REVIEW', icon: ClipboardCheck },
  { id: 'exports', label: '成果中心', caption: 'EXPORTS', icon: PackageCheck },
]
const activeNav = computed(() => navigation.find((item) => item.id === activeView.value))
const pendingReviews = computed(() => statistics.value.pending_reviews || 0)

async function loadDashboard() {
  loading.value = true
  const [healthResult, historyResult, statisticsResult, projectsResult] = await Promise.allSettled([
    fetchHealth(), fetchHistory(50), fetchStatistics(), fetchProjects(),
  ])
  health.value = healthResult.status === 'fulfilled' ? healthResult.value : { status: 'offline', engine: '服务未连接' }
  if (historyResult.status === 'fulfilled') history.value = historyResult.value
  if (statisticsResult.status === 'fulfilled') statistics.value = statisticsResult.value
  if (projectsResult.status === 'fulfilled') {
    projects.value = projectsResult.value
    if (!selectedProjectId.value && projects.value.length) selectedProjectId.value = projects.value[0].id
  }
  loading.value = false
}

function navigate(view) {
  activeView.value = view
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openAnalysis(analysis) {
  focusedAnalysis.value = analysis
  navigate('analysis')
}

function selectProject(projectId) {
  selectedProjectId.value = projectId
  navigate('projects')
}

function startProjectAnalysis(projectId) {
  selectedProjectId.value = projectId
  focusedAnalysis.value = null
  navigate('analysis')
}

function openReview(analysis, region) {
  focusedRegion.value = { ...region, analysis_id: analysis.id }
  navigate('review')
}

async function handleCompleted(analysis) {
  focusedAnalysis.value = analysis
  await loadDashboard()
}

onMounted(loadDashboard)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <button class="brand" type="button" aria-label="打开监测总览" @click="navigate('overview')">
        <span class="brand-mark"><Satellite :size="20" /></span>
        <span class="brand-copy"><strong>天山哨兵</strong><small>遥感变化监测平台</small></span>
      </button>
      <button class="new-analysis-button" type="button" @click="navigate('analysis')">
        <Plus :size="17" /><span>新建分析任务</span>
      </button>
      <nav aria-label="功能导航">
        <span class="nav-label">工作区</span>
        <button v-for="item in navigation" :key="item.id" type="button" :class="{ active: activeView === item.id }" @click="navigate(item.id)">
          <span><component :is="item.icon" :size="18" /></span>
          <span><strong>{{ item.label }}</strong></span>
          <i v-if="item.id === 'review' && pendingReviews">{{ pendingReviews }}</i>
        </button>
      </nav>
      <div class="sidebar-footer">
        <button class="sidebar-review-link" type="button" @click="navigate('review')">
          <Bell :size="17" /><span>待复核事项</span><strong>{{ pendingReviews }}</strong>
        </button>
        <div class="sidebar-system">
          <span class="sidebar-system-head"><i :class="health.status" />{{ health.status === 'offline' ? '服务离线' : '服务在线' }}</span>
          <strong>{{ health.engine }}</strong>
          <small>{{ statistics.total_analyses }} 次分析 · {{ statistics.total_regions }} 个斑块</small>
        </div>
      </div>
    </aside>

    <section class="workspace-shell">
      <header class="topbar app-topbar">
        <button class="mobile-brand" type="button" aria-label="打开监测总览" @click="navigate('overview')">
          <span class="brand-mark"><Satellite :size="18" /></span><strong>天山哨兵</strong>
        </button>
        <div class="topbar-breadcrumb"><strong>{{ activeNav?.label }}</strong><span>{{ activeNav?.caption }}</span></div>
        <div class="topbar-actions">
          <div class="system-state" :class="health.status"><span class="status-dot" /><span>{{ health.status === 'offline' ? '推理服务离线' : '推理服务在线' }}</span></div>
          <button class="notification-button" type="button" title="待复核事项" @click="navigate('review')"><Bell :size="18" /><span v-if="pendingReviews">{{ pendingReviews > 99 ? '99+' : pendingReviews }}</span></button>
        </div>
      </header>

      <nav class="mobile-nav" aria-label="移动端功能导航">
        <button v-for="item in navigation" :key="item.id" type="button" :class="{ active: activeView === item.id }" @click="navigate(item.id)">
          <component :is="item.icon" :size="18" /><span>{{ item.label.slice(0, 2) }}</span><i v-if="item.id === 'review' && pendingReviews" />
        </button>
      </nav>

      <main class="app-main" :class="{ loading }">
        <OverviewDashboard
          v-if="activeView === 'overview'"
          :statistics="statistics"
          :projects="projects"
          :history="history"
          :health="health"
          @navigate="navigate"
          @open-analysis="openAnalysis"
          @select-project="selectProject"
        />
        <AnalysisWorkbench
          v-else-if="activeView === 'analysis'"
          :projects="projects"
          :focused-analysis="focusedAnalysis"
          :selected-project-id="selectedProjectId"
          @completed="handleCompleted"
          @open-review="openReview"
        />
        <ProjectPortfolio
          v-else-if="activeView === 'projects'"
          :projects="projects"
          :selected-project-id="selectedProjectId"
          @refresh="loadDashboard"
          @selected="selectedProjectId = $event"
          @analyze="startProjectAnalysis"
        />
        <ReviewCenter v-else-if="activeView === 'review'" :focused-region="focusedRegion" @updated="loadDashboard" />
        <ExportCenter v-else :history="history" :projects="projects" />
      </main>
    </section>
  </div>
</template>
