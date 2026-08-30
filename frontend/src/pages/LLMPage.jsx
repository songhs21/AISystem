// src/pages/LLMPage.jsx
import { useState } from 'react'
import { client } from '../api/client'

export default function LLMPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function send() {
    if (!input.trim() || loading) return
    const userMsg = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('http://localhost:11434/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'qwen3:14b',
          messages: [...messages, userMsg],
          stream: false,
        }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.message?.content || '' }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `오류: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', width:'100%', height: '100%', flexDirection: 'column', padding: 16, gap: 12 }}>
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            background: m.role === 'user' ? 'var(--accent)' : 'var(--bg3)',
            padding: '8px 12px', borderRadius: 8, maxWidth: '70%',
            whiteSpace: 'pre-wrap', fontSize: 13,
          }}>
            {m.content}
          </div>
        ))}
        {loading && <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>생성 중...</div>}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="메시지 입력 (Shift+Enter 줄바꿈)"
          style={{ flex: 1, height: 64, resize: 'none' }}
        />
        <button className="btn btn-primary" onClick={send} disabled={loading}>
          전송
        </button>
      </div>
    </div>
  )
}
