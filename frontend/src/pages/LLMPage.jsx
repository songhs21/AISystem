// src/pages/LLMPage.jsx
import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { llmApi, systemApi, historyApi, API_BASE } from '../api/client'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import { toTagLine } from '../utils/tags'
import MemoryPanel from '../components/MemoryPanel'

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

const ROLE_LABEL = { user: '나', assistant: 'AI' }

const PROMPT_TARGETS = [
  ['T2I',   'positive', 'T2I 긍정'],
  ['T2I',   'negative', 'T2I 부정'],
  ['I2I',   'positive', 'I2I 긍정'],
  ['I2I',   'negative', 'I2I 부정'],
  ['video', 'positive', 'I2V 긍정'],
  ['video', 'negative', 'I2V 부정'],
]

function QuoteChips({ quotes, onRemove, variant = 'input' }) {
  if (!quotes?.length) return null
  const inBubble = variant === 'bubble'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: inBubble ? 6 : 0 }}>
      {quotes.map((q, i) => (
        <div key={q.key || i} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '4px 8px', borderRadius: 6, fontSize: 11,
          background: inBubble ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.06)',
          color: inBubble ? 'rgba(255,255,255,0.8)' : 'var(--text-dim)',
          borderLeft: '3px solid var(--text-dim)',
        }}>
          {q.image_path && (
            <img
              src={`${API_BASE}/api/system/image?path=${encodeURIComponent(q.image_path)}`}
              style={{ width: 32, height: 32, objectFit: 'cover', borderRadius: 4, flexShrink: 0 }}
            />
          )}
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {q.content ? `${ROLE_LABEL[q.role] || '인용'}: ${q.content}` : '이미지'}
          </span>
          {onRemove && (
            <button
              onClick={() => onRemove(q.key)}
              style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 12, padding: 0 }}
            >×</button>
          )}
        </div>
      ))}
    </div>
  )
}

export default function LLMPage({ onQuote }) {
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
  const [view, setView] = useState('chat')   // 'chat' | 'memory'

  // 히스토리 피커 (임시)
  const [attachedPath, setAttachedPath] = useState(null)   // 첨부 이미지 경로 (디스크 경로)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [quotes, setQuotes] = useState([])
  const fileInputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

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
    const sentQuotes = quotes.map(({ role, content, image_path }) => ({
      role: role || null, content: content || '', image_path: image_path || null,
    }))
    const userMsg = { role: 'user', content: text, elapsed_ms: null, image_path: sentPath, quotes: sentQuotes }
    setMessages(prev => [...prev, userMsg, { role: 'assistant', content: '', elapsed_ms: null }])
    setLoading(true)
    setError(null)
    // 입력/첨부/인용은 여기서 비우지 않음: 첫 토큰을 받은 시점에 비움 (전송 중에는 입력란 읽기 전용)

    const controller = new AbortController()
    abortRef.current = controller
    let gotToken = false   // 첫 토큰을 받으면 서버가 이 대화를 저장하게 됨

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
          quotes: sentQuotes,
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
                setQuotes([])
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
      // 토큰을 하나도 못 받았으면(서버 미저장) 낙관적 메시지 2개를 되돌리고 입력/첨부/인용은 유지
      if (!gotToken) setMessages(prev => prev.slice(0, -2))
      setLoading(false)
      abortRef.current = null
    }
  }

  function stopStream() {
    abortRef.current?.abort()
  }
  function addQuote(q) {
    setQuotes(prev => {
      const key = `${q.role || 'img'}::${q.image_path || ''}::${q.content || ''}`
      return prev.some(p => p.key === key) ? prev : [...prev, { ...q, key }]
    })
  }

  function removeQuote(key) {
    setQuotes(prev => prev.filter(q => q.key !== key))
  }

  async function newSession() {
    if (creating) return
    setView('chat')
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

  const [ctxMenu, setCtxMenu] = useState(null)   // { x, y, role, text, image }

  const [notice, setNotice] = useState(null)

  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 2000)
    return () => clearTimeout(t)
  }, [notice])

  function sendToPrompt(target, field, label) {
    const text = ctxMenu?.text
    if (!text) return
    const value = target === 'video' ? text.trim() : toTagLine(text)
    console.log('[quote] send', { target, field, value })
    onQuote?.({ target, append: true, [field]: value })
    setNotice(`${label} 프롬프트에 추가됨`)
  }

  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    const onKey = e => { if (e.key === 'Escape') close() }
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('keydown', onKey)
    }
  }, [ctxMenu])

  function handleContextMenu(e, m) {
    const sel = window.getSelection()
    const bubble = e.currentTarget
    const inBubble = sel && !sel.isCollapsed
      && bubble.contains(sel.anchorNode) && bubble.contains(sel.focusNode)
    const text = inBubble ? sel.toString().trim() : ''
    const image = e.target.tagName === 'IMG' && e.target.dataset.msgImage ? m.image_path : null
    if (!text && !image) return   // 기본 메뉴 유지
    e.preventDefault()
    setCtxMenu({ x: e.clientX, y: e.clientY, role: m.role, text, image })
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%' }}>
      {/* 세션 목록 */}
      <div style={{
        width: 200, flexShrink: 0, borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', padding: 12, gap: 8,
      }}>
        <div style={{ display: 'flex', gap: 4 }}>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={newSession} disabled={creating}>
            + 새 대화
          </button>
          <button
            className="btn btn-ghost"
            title="장기 메모리"
            onClick={() => setView(v => (v === 'memory' ? 'chat' : 'memory'))}
            style={view === 'memory' ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}}
          >🧠</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {sessions.map(s => (
          <div
            key={s.id}
            onClick={() => { setView('chat'); selectSession(s.id) }}
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
      <div style={{ display: view === 'chat' ? 'flex' : 'none', flex: 1, flexDirection: 'column', padding: 16, gap: 12, minWidth: 0 }}>
        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>
        )}

        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {sessionId === null && (
            <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>
              왼쪽에서 대화를 선택하거나 새 대화를 시작하세요.
            </div>
          )}
          {messages.map((m, i) => {
            const isStreaming = loading && i === messages.length - 1 && m.role === 'assistant'
            return (
              <div key={i} style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                display: 'flex', flexDirection: 'column', gap: 4, maxWidth: '70%', minWidth: 0,
                alignItems: m.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div
                  onContextMenu={e => handleContextMenu(e, m)}
                  style={{
                    background: m.role === 'user' ? 'var(--accent)' : 'var(--bg3)',
                    color: m.role === 'user' ? '#fff' : 'var(--text)',
                    padding: '8px 12px', borderRadius: 8,
                    minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere',
                    whiteSpace: (m.role === 'user' || isStreaming) ? 'pre-wrap' : 'normal',
                    fontSize: 13,
                    wordBreak: 'break-word',
                  }}
                >
                  <QuoteChips quotes={m.quotes} variant="bubble" />
                  {m.image_path && (
                    <img
                      data-msg-image="1"
                      src={`${API_BASE}/api/system/image?path=${encodeURIComponent(m.image_path)}`}
                      style={{ maxWidth: 200, maxHeight: 200, borderRadius: 6, display: 'block', marginBottom: 6 }}
                    />
                  )}
                  {m.role === 'user'
                    ? m.content
                    : isStreaming
                      ? (m.content || '...')
                      : <Markdown>{m.content}</Markdown>}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--text-dim)', fontSize: 11 }}>
                  {m.elapsed_ms != null && <span>{(m.elapsed_ms / 1000).toFixed(1)}초</span>}
                  {!isStreaming && m.content && (
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: '1px 6px' }}
                      onClick={() => addQuote({ role: m.role, content: m.content })}>
                      💬 인용
                    </button>
                  )}
                  {!isStreaming && m.image_path && (
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: '1px 6px' }}
                      onClick={() => addQuote({ role: m.role, image_path: m.image_path })}>
                      🖼️ 이미지 인용
                    </button>
                  )}
                </div>
              </div>
            )
          })}
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
          <QuoteChips quotes={quotes} onRemove={loading ? undefined : removeQuote} />

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
      {view === 'memory' && <MemoryPanel />}
      
      {ctxMenu && (
        <div
          style={{
            position: 'fixed',
            left: Math.min(ctxMenu.x, window.innerWidth - 190),
            top: Math.min(ctxMenu.y, window.innerHeight - 230),
            zIndex: 400, minWidth: 170, padding: 4,
            display: 'flex', flexDirection: 'column', gap: 2,
            background: 'var(--bg2)', border: '1px solid var(--border)',
            borderRadius: 6, boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
          }}
        >
          {ctxMenu.text && (
            <button className="btn btn-ghost" style={{ textAlign: 'left', fontSize: 12 }}
              onClick={() => addQuote({ role: ctxMenu.role, content: ctxMenu.text })}>
              💬 선택 텍스트 인용
            </button>
          )}
          {ctxMenu.image && (
            <button className="btn btn-ghost" style={{ textAlign: 'left', fontSize: 12 }}
              onClick={() => addQuote({ role: ctxMenu.role, image_path: ctxMenu.image })}>
              🖼️ 이미지 인용
            </button>
          )}
          {ctxMenu.text && (
            <>
              <div style={{ fontSize: 10, color: 'var(--text-dim)', padding: '6px 8px 2px' }}>
                프롬프트로 보내기 (기존 값 뒤에 추가)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                {PROMPT_TARGETS.map(([target, field, label]) => (
                  <button key={`${target}-${field}`} className="btn btn-ghost"
                    style={{ textAlign: 'left', fontSize: 11, padding: '4px 8px' }}
                    onClick={() => sendToPrompt(target, field, label)}>
                    {label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {notice && (
        <div style={{
          position: 'fixed', right: 16, bottom: 16, zIndex: 500,
          padding: '8px 14px', borderRadius: 8, fontSize: 12,
          background: 'var(--bg2)', border: '1px solid var(--accent)', color: 'var(--text)',
        }}>
          {notice}
        </div>
      )}
    </div>
  )
}