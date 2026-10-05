// src/components/MemoryPanel.jsx
import { useState, useEffect, useCallback } from 'react'
import { llmApi } from '../api/client'

const CATEGORIES = [['coding', '코딩'], ['image', '이미지'], ['general', '일반']]
const TYPES = [['preference', '선호'], ['decision', '결정'], ['fact', '사실'], ['roadmap', '계획']]
const label = (list, key) => list.find(([k]) => k === key)?.[1] || key

const chip = {
  padding: '1px 6px', borderRadius: 4, fontSize: 10,
  background: 'var(--bg3)', border: '1px solid var(--border)', color: 'var(--text-dim)',
}

function MemoryCard({ m, onChanged, onError }) {
  const [editing, setEditing] = useState(false)
  const [category, setCategory] = useState(m.category)
  const [type, setType] = useState(m.type)
  const [content, setContent] = useState(m.content)
  const [keywords, setKeywords] = useState(m.keywords.join(', '))
  const [busy, setBusy] = useState(false)

  async function patch(body) {
    setBusy(true)
    try {
      await llmApi.updateMemory(m.id, body)
      onChanged()
      return true
    } catch (e) {
      onError(e.response?.data?.detail || e.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    const ok = await patch({
      category, type, content,
      keywords: keywords.split(',').map(k => k.trim()).filter(Boolean),
      reviewed: true,
    })
    if (ok) setEditing(false)
  }

  function cancel() {
    setCategory(m.category); setType(m.type)
    setContent(m.content); setKeywords(m.keywords.join(', '))
    setEditing(false)
  }

  async function remove() {
    if (!confirm('이 메모리를 삭제할까요?')) return
    setBusy(true)
    try {
      await llmApi.deleteMemory(m.id)
      onChanged()
    } catch (e) {
      onError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {editing ? (
        <>
          <div style={{ display: 'flex', gap: 6 }}>
            <select value={category} onChange={e => setCategory(e.target.value)} style={{ width: 100, fontSize: 12 }}>
              {CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <select value={type} onChange={e => setType(e.target.value)} style={{ width: 100, fontSize: 12 }}>
              {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <textarea value={content} onChange={e => setContent(e.target.value)}
            style={{ height: 70, resize: 'vertical', fontSize: 12 }} />
          <input value={keywords} onChange={e => setKeywords(e.target.value)}
            placeholder="키워드 (쉼표로 구분, 최대 5개)" style={{ fontSize: 12 }} />
        </>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={chip}>{label(CATEGORIES, m.category)}</span>
            <span style={chip}>{label(TYPES, m.type)}</span>
            {!m.reviewed && <span style={{ ...chip, color: 'var(--gold-chip)', borderColor: 'var(--gold-chip)' }}>미검토</span>}
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-dim)' }}>
              #{m.id} · 세션 {m.session_id} · {m.created_at}
            </span>
          </div>
          <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{m.content}</div>
          {m.keywords.length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>🏷️ {m.keywords.join(', ')}</div>
          )}
        </>
      )}

      <div style={{ display: 'flex', gap: 6 }}>
        {editing ? (
          <>
            <button className="btn btn-primary" style={{ fontSize: 11, padding: '3px 10px' }} disabled={busy} onClick={save}>저장</button>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '3px 10px' }} disabled={busy} onClick={cancel}>취소</button>
          </>
        ) : (
          <>
            {!m.reviewed && (
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: '3px 10px' }} disabled={busy}
                onClick={() => patch({ reviewed: true })}>✓ 검토 완료</button>
            )}
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '3px 10px' }} disabled={busy}
              onClick={() => setEditing(true)}>✎ 수정</button>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '3px 10px', marginLeft: 'auto', color: 'var(--danger)' }}
              disabled={busy} onClick={remove}>삭제</button>
          </>
        )}
      </div>
    </div>
  )
}

export default function MemoryPanel() {
  const [category, setCategory] = useState('')
  const [onlyUnreviewed, setOnlyUnreviewed] = useState(true)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await llmApi.memories(category, onlyUnreviewed)
      setItems(res.data.memories)
      setError(null)
    } catch (e) {
      setError('메모리를 불러오지 못했습니다')
    } finally {
      setLoading(false)
    }
  }, [category, onlyUnreviewed])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', padding: 16, gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 600 }}>🧠 장기 메모리</span>
        <select value={category} onChange={e => setCategory(e.target.value)} style={{ width: 110, fontSize: 12 }}>
          <option value="">전체</option>
          {CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, margin: 0, cursor: 'pointer' }}>
          <input type="checkbox" checked={onlyUnreviewed}
            onChange={e => setOnlyUnreviewed(e.target.checked)} style={{ width: 'auto' }} />
          미검토만
        </label>
        <button className="btn btn-ghost" style={{ fontSize: 11, padding: '3px 10px' }} onClick={load}>🔄</button>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-dim)' }}>
          {loading ? '로딩 중...' : `${items.length}개`}
        </span>
      </div>

      {error && <div style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>}

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(m => (
          <MemoryCard key={m.id} m={m} onChanged={load} onError={setError} />
        ))}
        {!loading && items.length === 0 && (
          <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-dim)' }}>
            표시할 메모리가 없습니다.
          </div>
        )}
      </div>
    </div>
  )
}