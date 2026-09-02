// src/api/client.js
import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

export const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

// ── SD ────────────────────────────────────────────────────

export const sdApi = {
  checkpoints: () => client.get('/api/sd/checkpoints'),
  upscaleModels: () => client.get('/api/sd/upscale-models'),
  status: () => client.get('/api/sd/status'),

  // SSE 기반 — EventSource URL 반환
  generateUrl: () => `${API_BASE}/api/sd/generate`,
  upscaleUrl: () => `${API_BASE}/api/sd/upscale`,
  i2iUrl: () => `${API_BASE}/api/sd/i2i`,
  i2iMaskUrl: () => `${API_BASE}/api/sd/i2i-mask`,
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

// ── 시스템 ────────────────────────────────────────────────

export const systemApi = {
  status: () => client.get('/api/system/status'),
  switch: (mode, llm_model = 'qwen3:14b') =>
    client.post('/api/system/switch', { mode, llm_model }),
  uploadImage: (file) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/api/system/upload', form)
  },
}
