// src/api/client.js
import axios from 'axios'
import { crumb, sendClientLog } from '../utils/clientLog'


export const API_BASE = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

export const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

//Interceptor
const QUIET = ['/api/sd/queue', '/api/sd/status', '/api/sd/jobs/active',
               '/api/system/status', '/api/system/vram', '/api/system/ollama/vram']
const isQuiet = url => QUIET.some(p => (url || '').startsWith(p))

client.interceptors.response.use(
  res => {
    if (!isQuiet(res.config?.url)) {
      crumb(`${(res.config?.method || 'get').toUpperCase()} ${res.config?.url} → ${res.status}`)
    }
    return res
  },
  err => {
    const c = err.config || {}
    const method = (c.method || 'get').toUpperCase()
    const status = err.response?.status
    const detail = err.response?.data?.detail
    crumb(`${method} ${c.url} → ${status ?? 'ERR'}`)
    sendClientLog(
      status && status < 500 ? 'warn' : 'error',
      `API 실패 ${method} ${c.url} status=${status ?? 'network'} ${detail ? 'detail=' + String(detail).slice(0, 300) : err.message}`,
    )
    return Promise.reject(err)
  },
)
// ── SD ────────────────────────────────────────────────────

export const sdApi = {
  checkpoints: () => client.get('/api/sd/checkpoints'),
  upscaleModels: () => client.get('/api/sd/upscale-models'),
  loras: () => client.get('/api/sd/loras'), 
  status: () => client.get('/api/sd/status'),

  // SSE 기반 — EventSource URL 반환
  generateUrl: () => `${API_BASE}/api/sd/generate`,
  upscaleUrl: () => `${API_BASE}/api/sd/upscale`,
  i2iUrl: () => `${API_BASE}/api/sd/i2i`,
  i2iMaskUrl: () => `${API_BASE}/api/sd/i2i-mask`,
  i2vUrl: () => `${API_BASE}/api/sd/i2v`,
  activeJobs: (kind = 'i2v') => client.get('/api/sd/jobs/active', { params: { kind } }),
  jobStreamUrl: (jobId) => `${API_BASE}/api/sd/jobs/${jobId}/stream`,
  
  // ── 대기열 ────────────────────────────────────────────────
  queue: () => client.get('/api/sd/queue'),
  enqueueT2i: (payload) => client.post('/api/sd/queue/t2i', payload),
  enqueueI2i: (form) => client.post('/api/sd/queue/i2i', form),
  enqueueI2v: (payload) => client.post('/api/sd/queue/i2v', payload),
  removeQueueItem: (id) => client.delete(`/api/sd/queue/${id}`),
  clearQueue: () => client.delete('/api/sd/queue'),
  setQueueShutdown: (enabled) => client.post('/api/sd/queue/shutdown', { enabled }),
  abortQueueShutdown: () => client.post('/api/sd/queue/shutdown/abort'),
  reorderQueue: (ids) => client.post('/api/sd/queue/reorder', { ids }),
}

// ── 히스토리 ──────────────────────────────────────────────

export const historyApi = {
  generations: () => client.get('/api/history/generations'),
  generation: (id) => client.get(`/api/history/generations/${id}`),
  feedbacks: (gen_ids) => client.post('/api/history/feedbacks', { gen_ids }),
  saveFeedback: (data) => client.post('/api/history/feedback', data),
  tagWeights: (tags) => client.post('/api/history/tag-weights', { tags }),
  topTags: (category, limit = 10) => client.post('/api/history/top-tags', { category, limit }),
  inpaintings: (gen_id) => client.get(`/api/history/inpaintings/${gen_id}`),
  syncTags: () => client.post('/api/history/sync-tags'),
  vram: () => client.get('/api/system/vram'),
  comfyStart: () => client.post('/api/system/comfy/start'),
  comfyKill: () => client.post('/api/system/comfy/kill'),
  allTagWeights: () => client.get('/api/history/all-tag-weights'),
  i2iUrl: () => `${API_BASE}/api/sd/i2i`,
}

// ── 인페인팅 ──────────────────────────────────────────────

export const inpaintApi = {
  runUrl: () => `${API_BASE}/api/inpaint/run`,
}

// ── LLM ───────────────────────────────────────────────────

export const llmApi = {
  sessions: () => client.get('/api/llm/sessions'),
  createSession: (model) => client.post('/api/llm/sessions', null, { params: { model } }),
  history: (sessionId) => client.get(`/api/llm/history/${sessionId}`),
  chat: (message, sessionId, model, opts = {}) =>
    client.post('/api/llm/chat', {
      message,
      session_id: sessionId,
      model,
      image_path: opts.imagePath || null,
      quotes: opts.quotes || [],
    }, { timeout: 300000 }),
  deleteSession: (sessionId) => client.delete(`/api/llm/sessions/${sessionId}`),
  renameSession: (sessionId, title) => client.patch(`/api/llm/sessions/${sessionId}`, { title }),
  chatStreamUrl: () => `${API_BASE}/api/llm/chat-stream`,
  memories: (category, onlyUnreviewed = false) =>
    client.get('/api/llm/memories', {
      params: { category: category || undefined, only_unreviewed: onlyUnreviewed },
    }),
  updateMemory: (id, patch) => client.patch(`/api/llm/memories/${id}`, patch),
  deleteMemory: (id) => client.delete(`/api/llm/memories/${id}`),
}

export const ollamaApi = {
  start: () => client.post('/api/system/ollama/start'),
  kill: () => client.post('/api/system/ollama/kill'),
  vram: () => client.get('/api/system/ollama/vram'),
  unloadModel: (model) => client.post('/api/system/ollama/unload-model', null, { params: { model } }),
}

// ── 시스템 ────────────────────────────────────────────────
export const systemApi = {
  status: () => client.get('/api/system/status'),
  switch: (mode, llm_model = 'sorc/qwen3.5-instruct-heretic:9b') =>
    client.post('/api/system/switch', { mode, llm_model }),
  uploadImage: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/api/system/upload', form)
  },
  reveal: (path) => client.post('/api/system/reveal', { path }),

}
