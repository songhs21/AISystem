// src/utils/clientLog.js
const BASE = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
const originalFetch = window.fetch.bind(window)

const MAX_CRUMBS = 20
const crumbs = []

export function crumb(text) {
  crumbs.push(`${new Date().toTimeString().slice(0, 8)} ${text}`)
  if (crumbs.length > MAX_CRUMBS) crumbs.shift()
}

// 개발 모드에서만 콘솔 출력
export const dlog = (...args) => { if (import.meta.env.DEV) console.log(...args) }

let lastKey = ''
let lastAt = 0

export function sendClientLog(level, message, extra = {}) {
  try {
    const key = level + message
    const now = Date.now()
    if (key === lastKey && now - lastAt < 5000) return       // 같은 메시지 5초 내 중복 제거
    lastKey = key
    lastAt = now
    originalFetch(`${BASE}/api/system/client-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level,
        message: String(message).slice(0, 2000),
        stack: extra.stack ? String(extra.stack).slice(0, 5000) : null,
        url: window.location.href,
        breadcrumbs: [...crumbs],
      }),
      keepalive: true,
    }).catch(() => {})
  } catch { /* 로깅 실패는 무시 */ }
}

const shortUrl = u => String(u).replace(/^https?:\/\/[^/]+/, '').split('?')[0]

function describe(el) {
  const target = el?.closest?.('button, a, [role=button], input, select, textarea, label') || el
  if (!target?.tagName) return '?'
  const tag = target.tagName.toLowerCase()
  if (['input', 'textarea', 'select'].includes(tag)) return `<${tag}>`   // 입력 내용은 기록하지 않음
  const text = (target.getAttribute('aria-label') || target.title || target.innerText || target.id || '')
    .toString().trim().replace(/\s+/g, ' ').slice(0, 30)
  return `<${tag}>${text ? ` "${text}"` : ''}`
}

export function installClientLog() {
  if (window.__clientLogInstalled) return
  window.__clientLogInstalled = true

  window.addEventListener('error', e => {
    sendClientLog('error', e.message || 'window.error',
      { stack: e.error?.stack || `${e.filename}:${e.lineno}:${e.colno}` })
  })
  window.addEventListener('unhandledrejection', e => {
    const r = e.reason
    sendClientLog('error', `unhandledrejection: ${r?.message || r}`, { stack: r?.stack })
  })
  document.addEventListener('click', e => crumb(`click ${describe(e.target)}`), true)

  // fetch(SSE 포함) 호출 기록 + 실패 전송
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input?.url || String(input))
    const method = (init?.method || input?.method || 'GET').toUpperCase()
    const skip = url.includes('/api/system/client-log')
    try {
      const res = await originalFetch(input, init)
      if (!skip) {
        crumb(`${method} ${shortUrl(url)} → ${res.status}`)
        if (!res.ok) sendClientLog('warn', `HTTP ${res.status} ${method} ${shortUrl(url)}`)
      }
      return res
    } catch (err) {
      if (!skip && err?.name !== 'AbortError') {
        crumb(`${method} ${shortUrl(url)} ✕ ${err?.message}`)
        sendClientLog('error', `fetch 실패 ${method} ${shortUrl(url)}: ${err?.message}`, { stack: err?.stack })
      }
      throw err
    }
  }
}