// src/components/InpaintCanvas.jsx
import { useRef, useState, useEffect, useCallback } from 'react'
import { inpaintApi } from '../api/client'
import { API_BASE } from '../api/client'
import { useQuery } from '@tanstack/react-query'
import { sdApi } from '../api/client'

const MODES = ['영역 교체 (복장/배경)', '디테일 수정 (눈/손)']

const PROGRESS_BAR_H = 52  // px — 진행바 영역 높이

export default function InpaintCanvas({ imagePath, genId, checkpoint, prompt: initPrompt, onClose, onDone }) {
  const canvasRef         = useRef(null)
  const maskRef           = useRef(null)
  const imgRef            = useRef(null)
  const canvasViewportRef = useRef(null)
  const canvasStageRef    = useRef(null)
  const panStartRef       = useRef(null)
  const logBoxRef         = useRef(null)

  const [zoom, setZoom]         = useState(1)
  const [panning, setPanning]   = useState(false)
  const [offset, setOffset]     = useState({ x: 0, y: 0 })
  const [drawing, setDrawing]   = useState(false)
  const [brushSize, setBrushSize] = useState(30)
  const [mode, setMode]         = useState(MODES[0])
  const [prompt, setPrompt]     = useState(initPrompt || '')
  const [negative, setNegative] = useState('')
  const [denoise, setDenoise]   = useState(0.45)
  const [steps, setSteps]       = useState(35)
  const [running, setRunning]   = useState(false)
  const [hasStarted, setHasStarted] = useState(false)  // 한 번이라도 실행됐으면 true
  const [progress, setProgress] = useState(0)
  const [statusText, setStatusText] = useState('')
  const [resultSrc, setResultSrc]   = useState(null)
  const [logs, setLogs]         = useState([])          // 로그 누적
  const lastPos = useRef(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState(checkpoint || '')
  const { data: cpData } = useQuery({
    queryKey: ['checkpoints'],
    queryFn: () => sdApi.checkpoints().then(r => r.data),
  })
  const checkpoints = cpData?.checkpoints || []

  // props checkpoint로 초기화 (checkpoints 로드 후)
  useEffect(() => {
    if (checkpoint && !selectedCheckpoint) setSelectedCheckpoint(checkpoint)
  }, [checkpoint])

  // 로그 추가 헬퍼
  function addLog(text) {
    const time = new Date().toLocaleTimeString('ko-KR', { hour12: false })
    setLogs(prev => [...prev, `[${time}] ${text}`])
  }

  // 로그박스 자동 스크롤
  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
    }
  }, [logs])

  // 이미지 → 캔버스에 그리기
  useEffect(() => {
    const img = new Image()
    img.crossOrigin = 'anonymous'  
    img.onload = () => {
      const canvas  = canvasRef.current
      const mask    = maskRef.current
      const viewport = canvasViewportRef.current
      if (!canvas || !mask || !viewport) return

      const w = img.naturalWidth
      const h = img.naturalHeight

      canvas.width  = w
      canvas.height = h
      mask.width    = w
      mask.height   = h

      const vw = viewport.clientWidth
      const vh = viewport.clientHeight
      const scale = Math.min((vw * 0.9) / w, (vh * 0.9) / h)

      const displayW = w * scale
      const displayH = h * scale

      canvas.style.width  = `${displayW}px`
      canvas.style.height = `${displayH}px`
      mask.style.width    = `${displayW}px`
      mask.style.height   = `${displayH}px`

      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, w, h)
      ctx.drawImage(img, 0, 0)

      const mCtx = mask.getContext('2d')
      mCtx.clearRect(0, 0, w, h)

      setOffset({ x: (vw - displayW) / 2, y: (vh - displayH) / 2 })
      setZoom(1)
    }
    img.crossOrigin = 'anonymous'
    img.src = `${API_BASE}/api/system/image?path=${encodeURIComponent(imagePath)}&t=${Date.now()}`
    imgRef.current = img

    return () => { img.onload = null; img.onerror = null }
  }, [imagePath])

  // 좌표 변환
  function getPos(e) {
    const rect   = maskRef.current.getBoundingClientRect()
    const scaleX = maskRef.current.width  / rect.width
    const scaleY = maskRef.current.height / rect.height
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY }
  }

  function startDraw(e) {
    if (e.button !== 0) return
    e.stopPropagation()
    setDrawing(true)
    const pos = getPos(e)
    lastPos.current = pos

    const ctx = maskRef.current.getContext('2d')
    ctx.strokeStyle = 'rgba(255, 0, 0, 0.5)'
    ctx.lineWidth = brushSize
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.beginPath()          // path는 startDraw에서만 시작
    ctx.moveTo(pos.x, pos.y)
  }

  function draw(e) {
    if (!drawing) return
    if (e.buttons !== 1) return

    const { x, y } = getPos(e)
    const ctx = maskRef.current.getContext('2d')
    ctx.lineTo(x, y)
    ctx.stroke()

    lastPos.current = { x, y }
  }

  function stopDraw() {
    setDrawing(false)
    lastPos.current = null
    // path 닫기
    const ctx = maskRef.current?.getContext('2d')
    if (ctx) ctx.beginPath()
  }

  function stopDraw() { setDrawing(false) }

  function clearMask() {
    const ctx = maskRef.current.getContext('2d')
    ctx.clearRect(0, 0, maskRef.current.width, maskRef.current.height)
  }

  // 패닝 (휠 클릭)
  function handleMouseDown(e) {
    if (e.button !== 1) return
    e.preventDefault()
    e.stopPropagation()
    setPanning(true)
    panStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, offsetX: offset.x, offsetY: offset.y }
  }

  function handleMouseMove(e) {
    if (!panning || !panStartRef.current) return
    const s = panStartRef.current
    setOffset({ x: s.offsetX + (e.clientX - s.mouseX), y: s.offsetY + (e.clientY - s.mouseY) })
  }

  function handleMouseUp(e) {
    if (e.button !== 1 && e.buttons !== 0) return
    setPanning(false)
    panStartRef.current = null
  }

  // 휠 줌
  const handleWheel = useCallback((e) => {
    e.preventDefault()
    const viewport = canvasViewportRef.current
    const stage    = canvasStageRef.current
    if (!viewport || !stage) return

    const viewportRect = viewport.getBoundingClientRect()
    const stageRect    = stage.getBoundingClientRect()
    const mouseX = e.clientX - viewportRect.left
    const mouseY = e.clientY - viewportRect.top
    const delta  = e.deltaY < 0 ? 1.1 : 0.9

    setZoom(prevZoom => {
      const nextZoom = Math.min(Math.max(prevZoom * delta, 0.2), 8)
      if (nextZoom === prevZoom) return prevZoom
      const imageX = (e.clientX - stageRect.left) / prevZoom
      const imageY = (e.clientY - stageRect.top)  / prevZoom
      setOffset({ x: mouseX - imageX * nextZoom, y: mouseY - imageY * nextZoom })
      return nextZoom
    })
  }, [])

  useEffect(() => {
    const el = canvasViewportRef.current
    if (!el) return
    el.addEventListener('wheel', handleWheel, { passive: false })
    return () => el.removeEventListener('wheel', handleWheel)
  }, [handleWheel])

  // 인페인팅 실행
  async function runInpaint() {
    if (running) return
    setRunning(true)
    setHasStarted(true)
    setProgress(0)
    setStatusText('준비 중...')
    setResultSrc(null)
    setLogs([])
    addLog('인페인팅 시작')

    try {
      const imageBlob = await new Promise(res => canvasRef.current.toBlob(res, 'image/png'))
      const maskBlob  = await new Promise(res => {
        const tmp  = document.createElement('canvas')
        tmp.width  = maskRef.current.width
        tmp.height = maskRef.current.height
        const ctx  = tmp.getContext('2d')
        ctx.drawImage(maskRef.current, 0, 0)
        const imageData = ctx.getImageData(0, 0, tmp.width, tmp.height)
        const d = imageData.data
        for (let i = 0; i < d.length; i += 4) {
          const hasColor = d[i] > 50 || d[i + 1] > 50 || d[i + 2] > 50
          d[i] = d[i + 1] = d[i + 2] = hasColor ? 255 : 0
          d[i + 3] = 255
        }
        ctx.putImageData(imageData, 0, 0)
        tmp.toBlob(res, 'image/png')
      })

      const form = new FormData()
      form.append('gen_id',     genId)
      form.append('mode',       mode === MODES[1] ? 'detail' : 'replace')
      form.append('prompt',     prompt)
      form.append('negative',   negative)
      form.append('denoise',    denoise)
      form.append('steps',      steps)
      form.append('checkpoint', selectedCheckpoint || '')
      form.append('image',      imageBlob, 'image.png')
      form.append('mask',       maskBlob,  'mask.png')

      addLog('서버 전송 중...')
      const res     = await fetch(inpaintApi.runUrl(), { method: 'POST', body: form })
      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        let eventType = null
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (eventType === 'progress') {
              setProgress(data.value)
              setStatusText(data.text)
              addLog(data.text)
            } else if (eventType === 'done') {
              setProgress(1)
              setStatusText('✅ 완료!')
              addLog(`완료 — ${data.filename}`)
              const resultUrl = `${API_BASE}/api/system/image?path=${encodeURIComponent(data.image_path)}`
              setResultSrc(resultUrl)
              const img = new Image()
              img.crossOrigin = 'anonymous'
              img.onload = () => {
                const ctx = canvasRef.current.getContext('2d')
                ctx.drawImage(img, 0, 0)
              }
              img.src = `${resultUrl}&t=${Date.now()}`
              clearMask()
            } else if (eventType === 'error') {
              setStatusText(`❌ 오류: ${data.message}`)
              addLog(`오류: ${data.message}`)
            }
            eventType = null
          }
        }
      }
    } catch (e) {
      setStatusText(`❌ 오류: ${e.message}`)
      addLog(`예외: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  // ── JSX ──────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* 좌: 캔버스 영역 */}
      <div style={{ position: 'absolute', top: 52, left: 0, right: 280, bottom: 0, boxSizing: 'border-box' }}>

        {/* 상단 헤더 */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 52,
          padding: '0 16px', boxSizing: 'border-box',
          display: 'flex', alignItems: 'center', gap: 8,
          zIndex: 20, background: 'var(--bg)', borderBottom: '1px solid var(--border)',
        }}>
          <button className="btn btn-ghost" onClick={onClose}>← 뒤로</button>
          <span style={{ fontWeight: 600 }}>🖌️ 인페인팅</span>
          <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 8 }}>
            휠클릭 패닝 · 스크롤 줌
          </span>
          <button className="btn btn-ghost" onClick={clearMask} style={{ marginLeft: 'auto' }}>마스크 초기화</button>
        </div>

        {/* 캔버스 viewport — 진행바 높이만큼 bottom 확보 */}
        <div
          ref={canvasViewportRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{
            position: 'absolute',
            top: 52, left: 16, right: 16,
            bottom: hasStarted ? PROGRESS_BAR_H + 16 : 16,
            overflow: 'hidden',
            transition: 'bottom 0.2s',
          }}
        >
          <div
            ref={canvasStageRef}
            style={{
              position: 'absolute', left: 0, top: 0,
              transformOrigin: '0 0',
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
            }}
          >
            <canvas ref={canvasRef} style={{ display: 'block', borderRadius: 8 }} />
            <canvas
              ref={maskRef}
              style={{ position: 'absolute', top: 0, left: 0, cursor: 'crosshair' }}
              onMouseDown={startDraw}
              onMouseMove={draw}
              onMouseUp={stopDraw}
              onMouseLeave={stopDraw}
            />
          </div>
        </div>

        {/* 진행바 — 하단 고정, 한 번 실행 후 유지 */}
        {hasStarted && (
          <div style={{
            position: 'absolute', left: 16, right: 16,
            bottom: 16,
            height: PROGRESS_BAR_H,
            display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6,
          }}>
            <div className="progress-bar">
              <div className="progress-bar-fill" style={{ width: `${progress * 100}%` }} />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{statusText}</span>
          </div>
        )}
      </div>

      {/* 우: 설정 패널 */}
      <div style={{
        position: 'absolute', top: 52, right: 0, bottom: 0, width: 280,
        boxSizing: 'border-box', borderLeft: '1px solid var(--border)',
        padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
        overflowY: 'auto', zIndex: 30,
      }}>
        <div>
          <label>체크포인트</label>
          <select
            value={selectedCheckpoint}
            onChange={e => setSelectedCheckpoint(e.target.value)}
            style={{ fontSize: 12 }}
          >
            {checkpoints.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label>브러시 크기: {brushSize}</label>
          <input type="range" min={5} max={100} value={brushSize}
            onChange={e => setBrushSize(+e.target.value)}
            style={{ padding: 0, border: 'none', background: 'none' }} />
        </div>

        <div>
          <label>인페인팅 모드</label>
          {MODES.map(m => (
            <button key={m} className="btn btn-ghost" style={{
              width: '100%', marginBottom: 4, fontSize: 11,
              ...(mode === m ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {})
            }} onClick={() => setMode(m)}>{m}</button>
          ))}
        </div>

        <div>
          <label>프롬프트</label>
          <textarea value={prompt} onChange={e => setPrompt(e.target.value)}
            style={{ height: 80, resize: 'vertical' }} />
        </div>

        <div>
          <label>네거티브</label>
          <textarea value={negative} onChange={e => setNegative(e.target.value)}
            style={{ height: 60, resize: 'vertical' }} />
        </div>

        <div>
          <label>Denoise: {denoise}</label>
          <input type="range" min={0.1} max={1.0} step={0.05} value={denoise}
            onChange={e => setDenoise(+e.target.value)}
            style={{ padding: 0, border: 'none', background: 'none' }} />
        </div>

        <div>
          <label>Steps: {steps}</label>
          <input type="range" min={10} max={60} step={1} value={steps}
            onChange={e => setSteps(+e.target.value)}
            style={{ padding: 0, border: 'none', background: 'none' }} />
        </div>

        <button className="btn btn-primary" onClick={runInpaint} disabled={running}
          style={{ marginTop: 'auto' }}>
          {running ? '처리 중...' : '✅ 인페인팅 시작'}
        </button>

        {resultSrc && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <button
              className="btn btn-ghost"
              onClick={() => {
                // 캔버스를 원본 이미지로 되돌리기
                const ctx = canvasRef.current.getContext('2d')
                ctx.drawImage(imgRef.current, 0, 0)
                clearMask()
                setResultSrc(null)
                setProgress(0)
                setStatusText('')
              }}
            >
              🔄 완료 (재작업)
            </button>
            <button className="btn btn-ghost" onClick={onDone}>
              ✅ 히스토리로 돌아가기
            </button>
          </div>
        )}

        {/* 로그 텍스트박스 — 실행 후 표시 */}
        {hasStarted && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>실행 로그</span>
              <button
                className="btn btn-ghost"
                style={{ fontSize: 10, padding: '1px 6px' }}
                onClick={() => setLogs([])}
              >지우기</button>
            </label>
            <div
              ref={logBoxRef}
              style={{
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '6px 8px',
                fontSize: 10,
                lineHeight: 1.6,
                color: 'var(--text-dim)',
                fontFamily: 'monospace',
                maxHeight: 160,
                overflowY: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {logs.length === 0
                ? <span style={{ color: 'var(--border)' }}>로그 없음</span>
                : logs.map((l, i) => <div key={i}>{l}</div>)
              }
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
