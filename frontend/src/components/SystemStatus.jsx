import { useQuery } from '@tanstack/react-query'
import { client } from '../api/client'

export default function SystemStatus() {
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

  async function toggleComfy() {
    if (status?.sd) await client.post('/api/system/comfy/kill')
    else await client.post('/api/system/comfy/start')
  }

  async function unloadComfyModel() {
  await client.post('/api/system/comfy/unload')
  }

  // 상태별 색상 (꺼짐=빨강, 기동중=주황, 실행중=초록)
  const sdColor = !status?.sd ? 'var(--danger)' : 'var(--success)'
  const llmColor = !status?.llm ? 'var(--danger)' : 'var(--success)'

  const vramColor = vram
    ? vram.percent > 90 ? 'var(--danger)'
    : vram.percent > 70 ? '#f0a040'
    : 'var(--success)'
    : 'var(--text-dim)'

  return (
    <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, alignItems: 'center', fontSize: 12 }}>

      {/* VRAM 퍼센트 */}
      <span style={{ color: vramColor, fontWeight: 600 }}>
        {vram ? `VRAM ${vram.percent}% (${vram.used_gb}G / ${vram.total_gb}G)` : 'VRAM -'}
      </span>

      {/* ComfyUI 토글 */}
      <span onClick={toggleComfy} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
        title={status?.sd ? 'ComfyUI 종료' : 'ComfyUI 시작'}>
        <span className="status-dot" style={{ background: sdColor }} />
        <span style={{ color: sdColor }}>SD</span>
      </span>

      <button
        className="btn btn-ghost"
        onClick={unloadComfyModel}
      >
        모델 언로드
      </button>

      {/* LLM 상태 */}
      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span className="status-dot" style={{ background: llmColor }} />
        <span style={{ color: llmColor }}>LLM</span>
      </span>
    </div>
  )
}