import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { client, API_BASE } from '../api/client'

export default function SystemStatus() {
  const [comfyLoading, setComfyLoading] = useState(false)
  const [comfyStatus, setComfyStatus]   = useState('')
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmStatus, setLlmStatus] = useState('')
  const { data: status } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => client.get('/api/system/status').then(r => r.data),
    refetchInterval: 3000,
  })

  const { data: vram } = useQuery({
    queryKey: ['vram'],
    queryFn: () => client.get('/api/system/vram').then(r => r.data),
    refetchInterval: 1000,
    enabled: !!status?.sd,
  })
  const { data: llmVram } = useQuery({
    queryKey: ['llm-vram'],
    queryFn: () => client.get('/api/system/ollama/vram').then(r => r.data),
    refetchInterval: 1000,
    enabled: !!status?.llm,
  })

  const [comfyStatusText, setComfyStatusText] = useState('')
  const [comfyProgress, setComfyProgress] = useState(0)
  
  async function toggleComfy() {
    setComfyLoading(true)
    setComfyProgress(0)

    if (status?.sd) {
      setComfyStatus('stopping')
      await client.post('/api/system/comfy/kill')
      for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 1000))
        setComfyProgress((i + 1) / 15)
        const res = await client.get('/api/system/status')
        if (!res.data.sd) break
      }
      setComfyLoading(false)
      setComfyStatus('')
      setComfyProgress(0)
    } else {
      setComfyStatus('starting')
      const res = await fetch(`${API_BASE}/api/system/comfy/start-stream`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        let eventType = null
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (eventType === 'log') setComfyStatusText(data.text)
            else if (eventType === 'done') {
              setComfyLoading(false)
              setComfyStatus('')
              setComfyProgress(0)
            }
          }
        }
      }
    }
  }

  async function unloadComfyModel() {
    await client.post('/api/system/comfy/unload')
  }
  async function toggleLlm() {
    setLlmLoading(true)
    if (status?.llm) {
      setLlmStatus('stopping')
      await client.post('/api/system/ollama/kill')
      for (let i = 0; i < 10; i++) {
        await new Promise(r => setTimeout(r, 500))
        const res = await client.get('/api/system/status')
        if (!res.data.llm) break
      }
    } else {
      setLlmStatus('starting')
      await client.post('/api/system/ollama/start')
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1000))
        const res = await client.get('/api/system/status')
        if (res.data.llm) break
      }
    }
    setLlmLoading(false)
    setLlmStatus('')
  }

  async function unloadLlmModel() {
    await client.post('/api/system/ollama/unload-model', null, { params: { model: 'sorc/qwen3.5-instruct-heretic:9b' } })
  }
  const sdColor = !status?.sd ? 'var(--danger)' : 'var(--success)'
  const llmModelLoaded = !!llmVram?.model
  const llmColor = !status?.llm
    ? 'var(--danger)'
    : llmModelLoaded
      ? 'var(--success)'
      : 'var(--gold-chip)'
  const vramColor = vram
    ? vram.percent > 90 ? 'var(--danger)'
    : vram.percent > 70 ? '#f0a040'
    : 'var(--success)'
    : 'var(--text-dim)'

  return (
    <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, alignItems: 'center', fontSize: 12 }}>

      <div style={{ display: 'flex', flexDirection: 'column', fontSize: 11, lineHeight: 1.5 }}>
        <span style={{ color: vramColor, fontWeight: 600 }}>
          SD: {vram ? `${vram.percent}% (${vram.used_gb}G / ${vram.total_gb}G)` : '-'}
        </span>
        <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>
          LLM: {llmVram && vram?.total_gb
            ? `${Math.round(llmVram.used_gb / vram.total_gb * 100)}% (${llmVram.used_gb}G / ${vram.total_gb}G)`
            : status?.llm ? '언로드됨' : '-'}
        </span>
      </div>

      <span onClick={toggleComfy} style={{ cursor: comfyLoading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
        title={status?.sd ? 'ComfyUI 종료' : 'ComfyUI 시작'}>
        <span className="status-dot" style={{ background: sdColor }} />
        <span style={{ color: sdColor }}>SD</span>
      </span>

      {comfyLoading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            {comfyStatus === 'starting' ? '⏳ 시작 중...' : '⏳ 종료 중...'}
          </span>
          {comfyStatus === 'starting' && comfyStatusText && (
            <span style={{ fontSize: 10, color: 'var(--text-dim)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {comfyStatusText}
            </span>
          )}
          <div className="progress-bar" style={{ width: 80 }}>
            <div className="progress-bar-fill" style={{ width: `${comfyProgress * 100}%` }} />
          </div>
        </div>
      )}

      <button className="btn btn-ghost" onClick={unloadComfyModel}>
        모델 언로드
      </button>

      <span onClick={toggleLlm} style={{ cursor: llmLoading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
        title={
        !status?.llm
          ? 'Ollama 시작'
          : llmModelLoaded
            ? `Ollama 종료 (모델 로드됨: ${llmVram.model})`
            : 'Ollama 종료 (서버만 실행 중, 모델 언로드 상태)'
      }>
        <span className="status-dot" style={{ background: llmColor }} />
        <span style={{ color: llmColor }}>LLM</span>
      </span>

      {llmLoading && (
        <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          {llmStatus === 'starting' ? '⏳ 시작 중...' : '⏳ 종료 중...'}
        </span>
      )}

      <button className="btn btn-ghost" onClick={unloadLlmModel}>
        모델 언로드
      </button>
    </div>
  )
}