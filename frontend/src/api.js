import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1', timeout: 120000 })

export async function fetchHealth() {
  return (await api.get('/health')).data
}

export async function fetchHistory(limit = 50, projectId = null) {
  return (await api.get('/analyses', { params: { limit, project_id: projectId || undefined } })).data.items
}

export async function fetchAnalysis(analysisId) {
  return (await api.get(`/analyses/${analysisId}`)).data
}

export async function fetchStatistics() {
  return (await api.get('/statistics')).data
}

export async function fetchProjects() {
  return (await api.get('/projects')).data.items
}

export async function createProject(payload) {
  return (await api.post('/projects', payload)).data
}

export async function updateProject(projectId, payload) {
  return (await api.patch(`/projects/${projectId}`, payload)).data
}

export async function fetchTimeline(projectId) {
  return (await api.get(`/projects/${projectId}/timeline`)).data
}

export async function fetchReviews(status = 'pending') {
  return (await api.get('/reviews', { params: { status, limit: 500 } })).data
}

export async function reviewRegion(analysisId, regionId, payload) {
  return (await api.patch(`/analyses/${analysisId}/regions/${regionId}`, payload)).data
}

export async function analyzePair(before, after, options = {}) {
  const form = new FormData()
  form.append('before', before)
  form.append('after', after)
  if (options.projectId) form.append('project_id', options.projectId)
  form.append('before_label', options.beforeLabel || 'T1')
  form.append('after_label', options.afterLabel || 'T2')
  return (await api.post('/analyses', form)).data
}

export function analysisExportUrl(analysisId, type) {
  const paths = {
    docx: 'report.docx',
    pdf: 'report.pdf',
    geojson: 'regions.geojson',
  }
  return `/api/v1/analyses/${analysisId}/exports/${paths[type]}`
}

export function projectTimelineExportUrl(projectId) {
  return `/api/v1/projects/${projectId}/exports/timeline.csv`
}
