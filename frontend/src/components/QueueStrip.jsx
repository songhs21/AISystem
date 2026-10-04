// src/components/QueueStrip.jsx
import { API_BASE } from '../api/client'
import { useDragResize } from '../hooks/useDragResize'
import ResizeHandle from './ResizeHandle'

const imgSrc = p => `${API_BASE}/api/system/image?path=${encodeURIComponent(p)}`
const vidSrc = p => `${API_BASE}/api/system/video?path=${encodeURIComponent(p)}`
const shortName = s => (s || '').split(/[/\\]/).pop().replace(/\.(safetensors|ckpt)$/i, '')
const clip = (s, n = 300) => (s && s.length > n ? s.slice(0, n) + '…' : s)

// 큐 항목 → 뷰포트 메타 카드용 정보
export function itemMeta(item) {
  const s = item.summary || {}
  const meta = { 모드: s.mode, 체크포인트: s.checkpoint, 프롬프트: s.prompt, 네거티브: s.negative }
  if (s.mode === 'i2v') {
    Object.assign(meta, {
      시드: s.seed, 해상도: `${s.width}x${s.height}`, 프레임: s.length,
      스텝: `High ${s.high_steps} / Low ${s.low_steps}`, CFG: s.cfg,
    })
  } else {
    meta.LoRA = s.lora || '없음'
    if (s.mode === 'i2i') {
      Object.assign(meta, { Denoise: s.denoise, 시드: s.seed, 마스크: s.has_mask ? '있음' : '없음' })
    }
  }
  return meta
}

function thumbOf(item) {
  const r = item.result || {}
  if (item.status === 'done') {
    return item.kind === 'i2v'
      ? { type: 'video', src: vidSrc(r.video_path) }
      : { type: 'image', src: imgSrc(r.image_path) }
  }
  const base = item.summary?.base_image
  return base ? { type: 'image', src: imgSrc(base) } : null
}

const fill = { width: '100%', height: '100%', objectFit: 'cover', display: 'block' }
const overlayBase = {
  position: 'absolute', left: 0, right: 0, bottom: 0,
  padding: '2px 4px', fontSize: 10, color: '#fff',
  background: 'rgba(0,0,0,0.65)',
}

function QueueCard({ item, size, waitingNo, selected, onSelect, onRemove }) {
  const s = item.summary || {}
  const thumb = thumbOf(item)
  const isDone = item.status === 'done'
  const isError = item.status === 'error'
  const isRunning = item.status === 'running' || item.status === 'cancelling'

  const title = [
    `[${item.kind}] ${shortName(s.checkpoint)}`,
    s.prompt && `+ ${clip(s.prompt)}`,
    s.negative && `- ${clip(s.negative)}`,
    s.lora && `LoRA: ${s.lora}`,
    item.error && `오류: ${item.error}`,
  ].filter(Boolean).join('\n')

  return (
    <div
      title={title}
      onClick={() => (isDone || isRunning) && onSelect(item)}
      style={{
        position: 'relative', width: size, height: size, flexShrink: 0,
        borderRadius: 6, overflow: 'hidden', background: 'var(--bg3)',
        border: `2px solid ${selected ? 'var(--accent)' : isError ? 'var(--danger)' : 'var(--border)'}`,
        cursor: (isDone || isRunning) ? 'pointer' : 'default',
        opacity: item.status === 'waiting' ? 0.8 : 1,
      }}
    >
      {thumb ? (
        thumb.type === 'video'
          ? <video src={thumb.src} muted preload="metadata" style={fill} />
          : <img src={thumb.src} style={fill} />
      ) : (
        <div style={{ padding: 6, fontSize: 10, color: 'var(--text-dim)', overflow: 'hidden', wordBreak: 'break-all', lineHeight: 1.3 }}>
          {clip((s.prompt || '').split(',').slice(0, 4).join(', '), 60) || '(빈 프롬프트)'}
        </div>
      )}

      <span style={{
        position: 'absolute', top: 2, left: 2, padding: '0 4px', borderRadius: 3,
        fontSize: 9, color: '#fff', background: 'rgba(0,0,0,0.65)',
      }}>{item.kind}</span>

      <button
        title={isRunning ? '중단' : isError || isDone ? '목록에서 제거' : '대기열에서 제거'}
        onClick={e => { e.stopPropagation(); onRemove(item) }}
        style={{
          position: 'absolute', top: 2, right: 2, width: 16, height: 16, padding: 0,
          border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: 11, lineHeight: '16px',
          color: '#fff', background: 'rgba(0,0,0,0.65)',
        }}
      >×</button>

      {item.status === 'waiting' && <div style={overlayBase}>대기 #{waitingNo}</div>}
      {isError && <div style={{ ...overlayBase, background: 'rgba(224,85,85,0.85)' }}>⚠ 실패</div>}
      {isRunning && (
        <div style={{ ...overlayBase, padding: 0 }}>
          <div style={{ height: 3, background: 'rgba(255,255,255,0.25)' }}>
            <div style={{ height: '100%', width: `${(item.progress || 0) * 100}%`, background: 'var(--accent)' }} />
          </div>
          <div style={{ padding: '2px 4px' }}>
            {item.status === 'cancelling' ? '취소 중...' : `${Math.round((item.progress || 0) * 100)}%`}
          </div>
        </div>
      )}
    </div>
  )
}

export default function QueueStrip({
  items, open, onToggle, selectedId, onSelect, onRemove, onClearPending,
  shutdown = { armed: false, remaining: 0 }, onToggleShutdown, onAbortShutdown,
  cardSize = 88, onCardSizeChange,
}) {
  const resize = useDragResize({
    value: cardSize, onChange: v => onCardSizeChange?.(v),
    min: 56, max: 220, axis: 'y', dir: 1,
  })
  const pendingCount = items.filter(i => ['waiting', 'running', 'cancelling'].includes(i.status)).length
  const waitingNo = {}
  let n = 0
  items.forEach(i => { if (i.status === 'waiting') waitingNo[i.id] = ++n })

  return (
    <div style={{ position: 'relative', flexShrink: 0, zIndex: 70 }}>
      {open && (
        <div style={{ position: 'relative', background: 'var(--bg2)', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px 0' }}>
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              {pendingCount > 0 ? `진행·대기 ${pendingCount}개` : `${items.length}개`}
            </span>

            {shutdown.remaining > 0 && (
              <span style={{ fontSize: 11, color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 6 }}>
                ⏻ PC가 {shutdown.remaining}초 후 종료됩니다
                <button className="btn btn-danger" style={{ fontSize: 11, padding: '2px 8px' }} onClick={onAbortShutdown}>
                  종료 취소
                </button>
              </span>
            )}

            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              {pendingCount > 0 && (
                <>
                  <button className="btn btn-ghost"
                    title="대기열의 모든 작업이 끝나면 PC를 종료합니다"
                    style={{
                      fontSize: 11, padding: '2px 8px',
                      ...(shutdown.armed ? { borderColor: 'var(--danger)', color: 'var(--danger)' } : {}),
                    }}
                    onClick={onToggleShutdown}>
                    ⏻ 완료 시 PC 종료{shutdown.armed ? ' 켜짐' : ''}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={onClearPending}>
                    전체 취소
                  </button>
                </>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, padding: '4px 12px 10px', overflowX: 'auto' }}>
            {items.length === 0 ? (
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>생성 요청이 여기에 쌓입니다</span>
            ) : items.map(item => (
              <QueueCard
                key={item.id}
                item={item}
                size={cardSize}
                waitingNo={waitingNo[item.id]}
                selected={item.id === selectedId}
                onSelect={onSelect}
                onRemove={onRemove}
              />
            ))}

            <ResizeHandle axis="y" style={{ bottom: 0 }} {...resize} onDoubleClick={() => onCardSizeChange?.(88)} />
          </div>
        </div>
      )}

      <button
        onClick={onToggle}
        style={{
          position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)',
          width: 100, height: 30,
          border: '1px solid var(--border)', borderTop: 'none', borderRadius: '0 0 12px 12px',
          background: 'var(--bg2)', color: 'var(--text-dim)', fontSize: 12, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
        }}
      >
        {open ? '▲' : '▼'} 대기열{pendingCount > 0 ? ` ${pendingCount}` : ''}
      </button>
    </div>
  )
}