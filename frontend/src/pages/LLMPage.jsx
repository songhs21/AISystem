// src/pages/LLMPage.jsx
import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { llmApi, systemApi, historyApi, API_BASE } from '../api/client'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
// ── 히스토리 이미지 피커 ──────────────────────────────────
function HistoryImagePicker({ onPick, onClose }) {
  const { data: gensData } = useQuery({
    queryKey: ['generations'],
    queryFn: () => historyApi.generations().then(r => r.data),
  })
  const generations = gensData?.generations || []

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 300,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg2)', border: '1px solid var(--border)',
          borderRadius: 10, padding: 16, width: 600, maxHeight: '80vh',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600 }}>히스토리에서 이미지 선택</span>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={onClose}>✕</button>
        </div>
        <div style={{ overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {generations.map(gen => {
            const src = `${API_BASE}/api/system/image?path=${encodeURIComponent(gen.image_path)}`
            return (
              <img
                key={gen.id}
                src={src}
                onClick={() => onPick(gen)}
                style={{
                  width: 100, height: 100, objectFit: 'cover',
                  borderRadius: 6, cursor: 'pointer',
                  border: '2px solid transparent',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'transparent'}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default function LLMPage() {
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')

  // 히스토리 피커 (임시)
  const [attachedPath, setAttachedPath] = useState(null)   // 첨부 이미지 경로 (디스크 경로)
const [pickerOpen, setPickerOpen] = useState(false)
const [useHistoryImages, setUseHistoryImages] = useState(false)
const [maxHistoryImages, setMaxHistoryImages] = useState(2)
const [dragOver, setDragOver] = useState(false)
const fileInputRef = useRef(null)

const abortRef = useRef(null)
  // 세션 목록 로드
  useEffect(() => {
    loadSessions()
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  async function loadSessions() {
    try {
      const res = await llmApi.sessions()
      setSessions(res.data)
      if (res.data.length > 0 && sessionId === null) {
        selectSession(res.data[0].id)
      }
    } catch (e) {
      setError('세션 목록을 불러오지 못했습니다')
    }
  }

  async function selectSession(id) {
    setSessionId(id)
    try {
      const res = await llmApi.history(id)
      setMessages(res.data.messages)
    } catch (e) {
      setError('대화 기록을 불러오지 못했습니다')
    }
  }

  // ── 마크다운 렌더러 ──────────────────────────────────────
  function Markdown({ children }) {
    return (
      <div className="md-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            a: ({ node, ...props }) => (
              <a {...props} target="_blank" rel="noopener noreferrer" />
            ),
          }}
        >
          {children}
        </ReactMarkdown>
      </div>
    )
  }
  // 히스토리 피커(임시)
  async function uploadAndAttach(file) {
  if (!file || loading || !file.type.startsWith('image/')) return
  try {
    const ext = (file.name.split('.').pop() || 'png').toLowerCase()
    file = new File([file], `llm_${Date.now()}.${ext}`, { type: file.type })
    const res = await systemApi.uploadImage(file)
    setAttachedPath(res.data.path)
  } catch (e) {
    setError('이미지 업로드에 실패했습니다')
  }
}

function handlePaste(e) {
  const item = Array.from(e.clipboardData?.items || []).find(i => i.type.startsWith('image/'))
  if (item) {
    e.preventDefault()
    uploadAndAttach(item.getAsFile())
  }
}

function handleDrop(e) {
  e.preventDefault()
  setDragOver(false)
  const file = Array.from(e.dataTransfer?.files || []).find(f => f.type.startsWith('image/'))
  if (file) uploadAndAttach(file)
}

  // 히스토리 피커 send(임시)
  async function send() {
    if (!input.trim() || loading || sessionId === null) return
    const text = input
    const sentPath = attachedPath
    const userMsg = { role: 'user', content: text, elapsed_ms: null, image_path: sentPath }
    setMessages(prev => [...prev, userMsg, { role: 'assistant', content: '', elapsed_ms: null }])
    setLoading(true)
    setError(null)
    // 입력/첨부는 여기서 비우지 않음: 첫 토큰을 받은 시점에 비움 (전송 중에는 입력란 읽기 전용)

    const controller = new AbortController()
    abortRef.current = controller
    let gotToken = false   // 첫 토큰을 받으면 서버가 이 대화를 저장하게 됨

    // 마지막 assistant 메시지(방금 추가한 빈 메시지)를 갱신하는 헬퍼
    const updateLast = (patch) =>
      setMessages(prev => {
        const next = [...prev]
        next[next.length - 1] = { ...next[next.length - 1], ...patch(next[next.length - 1]) }
        return next
      })

    try {
      const res = await fetch(llmApi.chatStreamUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          image_path: sentPath,
          use_history_images: useHistoryImages,
          max_history_images: maxHistoryImages,
        }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}))
        throw new Error(errBody.detail || `HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let eventType = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (eventType === 'token') {
              if (!gotToken) {
                gotToken = true
                setInput('')
                setAttachedPath(null)
              }
              updateLast(m => ({ content: m.content + data.text }))
            } else if (eventType === 'done') {
              updateLast(() => ({ elapsed_ms: data.elapsed_ms }))
            } else if (eventType === 'error') {
              setError(data.message)
            }
            eventType = null
          }
        }
      }
      loadSessions()
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      // 토큰을 하나도 못 받았으면(서버 미저장) 낙관적 메시지 2개를 되돌리고 입력/첨부는 유지
      if (!gotToken) setMessages(prev => prev.slice(0, -2))
      setLoading(false)
      abortRef.current = null
    }
  }

  function stopStream() {
    abortRef.current?.abort()
  }

  async function newSession() {
    if (creating) return
    setCreating(true)
    try {
      const res = await llmApi.createSession()
      await loadSessions()
      selectSession(res.data.id)
    } catch (e) {
      setError('새 세션을 만들지 못했습니다')
    } finally {
      setCreating(false)
    }
  }

  async function deleteSession(id, e) {
    e.stopPropagation()
    if (!confirm('이 대화를 삭제할까요?')) return
    try {
      await llmApi.deleteSession(id)
      if (id === sessionId) {
        setSessionId(null)
        setMessages([])
      }
      await loadSessions()
    } catch (e) {
      setError('세션 삭제에 실패했습니다')
    }
  }

  function startEdit(s, e) {
    e.stopPropagation()
    setEditingId(s.id)
    setEditTitle(s.title)
  }

  async function saveEdit(id) {
    const title = editTitle.trim()
    setEditingId(null)
    if (!title) return
    try {
      await llmApi.renameSession(id, title)
      await loadSessions()
    } catch (e) {
      setError('제목 수정에 실패했습니다')
    }
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%' }}>
      {/* 세션 목록 */}
      <div style={{
        width: 200, flexShrink: 0, borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', padding: 12, gap: 8,
      }}>
        <button className="btn btn-primary" onClick={newSession} disabled={creating}>
          + 새 대화
        </button>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {sessions.map(s => (
          <div
            key={s.id}
            onClick={() => selectSession(s.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '6px 8px', borderRadius: 6, cursor: 'pointer',
              border: '1px solid ' + (s.id === sessionId ? 'var(--accent)' : 'var(--border)'),
              background: 'var(--bg3)',
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              {editingId === s.id ? (
                <input
                  autoFocus
                  value={editTitle}
                  onChange={e => setEditTitle(e.target.value)}
                  onClick={e => e.stopPropagation()}
                  onKeyDown={e => {
                    if (e.key === 'Enter') saveEdit(s.id)
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  onBlur={() => saveEdit(s.id)}
                  style={{ fontSize: 12, padding: '2px 4px' }}
                />
              ) : (
                <>
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>
                    {s.title}
                  </div>
                  <div style={{ color: 'var(--text-dim)', fontSize: 10 }}>{s.model}</div>
                </>
              )}
            </div>
            {editingId !== s.id && (
              <>
                <button
                  onClick={e => startEdit(s, e)}
                  title="이름 수정"
                  style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 12, padding: 2 }}
                >
                  ✎
                </button>
                <button
                  onClick={e => deleteSession(s.id, e)}
                  title="삭제"
                  style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 12, padding: 2 }}
                >
                  ✕
                </button>
              </>
            )}
          </div>
        ))}
        </div>
      </div>

      {/* 채팅 영역 */}
      <div style={{ display: 'flex', flex: 1, flexDirection: 'column', padding: 16, gap: 12, minWidth: 0 }}>
        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>
        )}

        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {sessionId === null && (
            <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>
              왼쪽에서 대화를 선택하거나 새 대화를 시작하세요.
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              display: 'flex', flexDirection: 'column', gap: 4, maxWidth: '70%', minWidth: 0,
              alignItems: m.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{
                background: m.role === 'user' ? 'var(--accent)' : 'var(--bg3)',
                color: m.role === 'user' ? '#fff' : 'var(--text)',
               padding: '8px 12px', borderRadius: 8,
                minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere',
                whiteSpace: (m.role === 'user' || (loading && i === messages.length - 1)) ? 'pre-wrap' : 'normal',
                  fontSize: 13,
                  wordBreak: 'break-word',
              }}>
              {m.image_path && (
                  <img
                    src={`${API_BASE}/api/system/image?path=${encodeURIComponent(m.image_path)}`}
                    style={{ maxWidth: 200, maxHeight: 200, borderRadius: 6, display: 'block', marginBottom: 6 }}
                  />
                )}
                {(() => {
                  const isStreaming = loading && i === messages.length - 1 && m.role === 'assistant'
                  if (m.role === 'user') return m.content
                  if (isStreaming) return m.content || '...'
                  return <Markdown>{m.content}</Markdown>
                })()}
              </div>
              {m.elapsed_ms != null && (
                <div style={{ color: 'var(--text-dim)', fontSize: 11 }}>
                  {(m.elapsed_ms / 1000).toFixed(1)}초
                </div>
              )}
            </div>
          ))}
        </div>

        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          style={{
            display: 'flex', flexDirection: 'column', gap: 6,
            outline: dragOver ? '2px dashed var(--accent)' : 'none', borderRadius: 8,
          }}
        >
          {attachedPath && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <img
                src={`${API_BASE}/api/system/image?path=${encodeURIComponent(attachedPath)}`}
                style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 6 }}
              />
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
                disabled={loading} onClick={() => setAttachedPath(null)}>
                ✕ 제거
              </button>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--text-dim)' }}>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
              disabled={loading} onClick={() => fileInputRef.current?.click()}>
              📎 파일
            </button>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
              disabled={loading} onClick={() => setPickerOpen(true)}>
              🖼️ 히스토리
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={e => { uploadAndAttach(e.target.files?.[0]); e.target.value = '' }}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, margin: 0, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={useHistoryImages}
                onChange={e => setUseHistoryImages(e.target.checked)}
                style={{ width: 'auto' }}
              />
              이전 이미지 참조
            </label>
            {useHistoryImages && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 4, margin: 0 }}>
                최대
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={maxHistoryImages}
                  onChange={e => setMaxHistoryImages(Math.max(1, Number(e.target.value) || 1))}
                  style={{ width: 50, padding: '2px 4px' }}
                />
                장
              </label>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onPaste={handlePaste}
              readOnly={loading}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="메시지 입력 (Shift+Enter 줄바꿈, 이미지 붙여넣기/드롭 가능)"
              style={{ flex: 1, height: 64, resize: 'none', opacity: loading ? 0.6 : 1 }}
              disabled={sessionId === null}
            />
            {loading ? (
              <button className="btn btn-danger" style={{ minWidth: 64 }} onClick={stopStream}>
                중단
              </button>
            ) : (
              <button className="btn btn-primary" style={{ minWidth: 64 }} onClick={send} disabled={sessionId === null}>
                전송
              </button>
            )}
          </div>
        </div>

        {pickerOpen && (
          <HistoryImagePicker
            onClose={() => setPickerOpen(false)}
            onPick={gen => { setAttachedPath(gen.image_path); setPickerOpen(false) }}
          />
        )}
      </div>
    </div>
  )
}