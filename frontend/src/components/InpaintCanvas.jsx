// src/components/InpaintCanvas.jsx
import { useRef, useState, useEffect, useCallback } from 'react'
import { inpaintApi } from '../api/client'
import { API_BASE } from '../api/client'

const MODES = ['영역 교체 (복장/배경)', '디테일 수정 (눈/손)']

export default function InpaintCanvas({ imagePath, genId, checkpoint, prompt: initPrompt, onClose, onDone }) {
  const canvasRef  = useRef(null)
  const maskRef    = useRef(null)
  const imgRef     = useRef(null)
  const leftPanelRef = useRef(null)
  const canvasViewportRef = useRef(null)
  const initialScaleRef = useRef(1)
  const canvasStageRef = useRef(null)
  const [zoom, setZoom] = useState(1)
  const [panning, setPanning] = useState(false)
  const panStartRef = useRef(null)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [drawing, setDrawing]   = useState(false)
  const [brushSize, setBrushSize] = useState(30)
  const [mode, setMode]         = useState(MODES[0])
  const [prompt, setPrompt]     = useState(initPrompt || '')
  const [negative, setNegative] = useState('')
  const [denoise, setDenoise]   = useState(0.45)
  const [steps, setSteps]       = useState(35)
  const [running, setRunning]   = useState(false)
  const [progress, setProgress] = useState(0)
  const [statusText, setStatusText] = useState('')
  const [resultSrc, setResultSrc]   = useState(null)
  const [imgSize, setImgSize]   = useState({ w: 0, h: 0 })

  // 이미지 → 캔버스에 그리기
  useEffect(() => {
    console.log('[Inpaint] imagePath:', imagePath)

    const img = new Image()

    img.onload = () => {
      console.log('[Inpaint] loaded:', img.naturalWidth, img.naturalHeight)

      const canvas = canvasRef.current
      const mask = maskRef.current
      const viewport = canvasViewportRef.current

      if (!canvas || !mask || !viewport) {
        console.error('[Inpaint] ref missing')
        return
      }

      const w = img.naturalWidth
      const h = img.naturalHeight

      // 실제 캔버스 해상도
      canvas.width = w
      canvas.height = h

      mask.width = w
      mask.height = h

      // viewport 크기
      const vw = viewport.clientWidth
      const vh = viewport.clientHeight

      // 화면의 90% 안에 들어오도록 초기 표시 크기
      const scale = Math.min(
        (vw * 0.9) / w,
        (vh * 0.9) / h
      )

      initialScaleRef.current = scale

      // CSS 표시 크기
      const displayW = w * scale
      const displayH = h * scale

      canvas.style.width = `${displayW}px`
      canvas.style.height = `${displayH}px`

      mask.style.width = `${displayW}px`
      mask.style.height = `${displayH}px`

      // 이미지 그리기
      const ctx = canvas.getContext('2d')

      ctx.clearRect(0, 0, w, h)
      ctx.drawImage(img, 0, 0)

      // 마스크 초기화
      const mCtx = mask.getContext('2d')
      mCtx.clearRect(0, 0, w, h)

      // 중앙 배치
      setOffset({
        x: (vw - displayW) / 2,
        y: (vh - displayH) / 2,
      })

      setZoom(1)

      console.log('[Inpaint] canvas:', {
        w,
        h,
        vw,
        vh,
        scale,
        displayW,
        displayH,
      })
    }

    img.onerror = (e) => {
      console.error('[Inpaint] image load error:', e)
    }

    img.src =
      `${API_BASE}/api/system/image?path=${encodeURIComponent(imagePath)}`

    imgRef.current = img

    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [imagePath])


  // 좌표 변환 (display → 실제 canvas)
  function getPos(e) {
    const rect = maskRef.current.getBoundingClientRect()
    const scaleX = maskRef.current.width  / rect.width
    const scaleY = maskRef.current.height / rect.height
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top)  * scaleY,
    }
  }

  function startDraw(e) {
    // 가운데 버튼(휠 클릭)은 패닝 전용
    if (e.button !== 0) return

    e.stopPropagation()

    setDrawing(true)
    draw(e)
  }

  function draw(e) {
    if (!drawing) return
    if (e.buttons !== 1) return

    const { x, y } = getPos(e)
    const ctx = maskRef.current.getContext('2d')

    ctx.fillStyle = 'rgba(255, 0, 0, 0.5)'
    ctx.beginPath()
    ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2)
    ctx.fill()
  }

  function stopDraw() { setDrawing(false) }

  function clearMask() {
    const ctx = maskRef.current.getContext('2d')
    ctx.clearRect(0, 0, maskRef.current.width, maskRef.current.height)
  }

  function handleMouseDown(e) {
    if (e.button !== 1) return

    e.preventDefault()
    e.stopPropagation()

    setPanning(true)

    panStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      offsetX: offset.x,
      offsetY: offset.y,
    }
  }

function handleMouseMove(e) {
  if (!panning || !panStartRef.current) return

  const start = panStartRef.current

  setOffset({
    x: start.offsetX + (e.clientX - start.mouseX),
    y: start.offsetY + (e.clientY - start.mouseY),
  })
}

function handleMouseUp(e) {
  if (e.button !== 1 && e.buttons !== 0) return

  setPanning(false)
  panStartRef.current = null
}

function handleMouseMove(e) {
  if (!panning || !panStartRef.current) return

  const start = panStartRef.current

  setOffset({
    x: start.offsetX + (e.clientX - start.mouseX),
    y: start.offsetY + (e.clientY - start.mouseY),
  })
}

function handleMouseUp(e) {
  if (e.button !== 1 && e.buttons !== 0) return

  setPanning(false)
  panStartRef.current = null
}

  function handleMouseMove(e) {
    if (!panning || !panStartRef.current) return

    const start = panStartRef.current

    setOffset({
      x: start.offsetX + (e.clientX - start.mouseX),
      y: start.offsetY + (e.clientY - start.mouseY),
    })
  }

  const handleWheel = useCallback((e) => {
  e.preventDefault()

  const viewport = canvasViewportRef.current
  const stage = canvasStageRef.current

  if (!viewport || !stage) return

  const viewportRect = viewport.getBoundingClientRect()
  const stageRect = stage.getBoundingClientRect()

  // 마우스 위치: viewport 기준
  const mouseX = e.clientX - viewportRect.left
  const mouseY = e.clientY - viewportRect.top

  const delta = e.deltaY < 0 ? 1.1 : 0.9

  setZoom(prevZoom => {
    const nextZoom = Math.min(
      Math.max(prevZoom * delta, 0.2),
      8
    )

    if (nextZoom === prevZoom) {
      return prevZoom
    }

    /*
     * 현재 마우스가 이미지의 어느 지점을 가리키고 있는지 계산
     *
     * stageRect.left/top = 현재 화면에서 이미지의 좌상단
     * prevZoom            = 현재 확대 배율
     */
    const imageX = (e.clientX - stageRect.left) / prevZoom
    const imageY = (e.clientY - stageRect.top) / prevZoom

    /*
     * 확대 후에도 동일한 imageX/Y가
     * 마우스 포인터 바로 아래에 있도록 offset 재계산
     */
    setOffset({
      x: mouseX - imageX * nextZoom,
      y: mouseY - imageY * nextZoom,
    })

    return nextZoom
  })
}, [])

  useEffect(() => {
    const el = canvasViewportRef.current
    if (!el) return

    el.addEventListener('wheel', handleWheel, { passive: false })

    return () => {
      el.removeEventListener('wheel', handleWheel)
    }
  }, [handleWheel])

  // 인페인팅 실행
  async function runInpaint() {
    if (running) return
    setRunning(true)
    setProgress(0)
    setStatusText('준비 중...')
    setResultSrc(null)

    try {
      // 캔버스 → Blob
      const imageBlob = await new Promise(res => canvasRef.current.toBlob(res, 'image/png'))
      const maskBlob  = await new Promise(res => {
        // 마스크: 붉은 영역을 흰색으로 변환
        const tmp = document.createElement('canvas')
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
      form.append('checkpoint', checkpoint || '')
      form.append('image',      imageBlob, 'image.png')
      form.append('mask',       maskBlob,  'mask.png')

      const res = await fetch(inpaintApi.runUrl(), { method: 'POST', body: form })
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
            if (eventType === 'progress') {
              setProgress(data.value)
              setStatusText(data.text)
            } else if (eventType === 'done') {
              setProgress(1)
              setStatusText('완료!')
              const resultUrl =
                `${API_BASE}/api/system/image?path=${encodeURIComponent(data.image_path)}`

              setResultSrc(resultUrl)

              // 캔버스에 결과 반영
              const img = new Image()
              img.onload = () => {
                const ctx = canvasRef.current.getContext('2d')
                ctx.drawImage(img, 0, 0)
              }
              img.src = resultUrl
              clearMask()
            } else if (eventType === 'error') {
              setStatusText(`오류: ${data.message}`)
            }
            eventType = null
          }
        }
      }
    } catch (e) {
      setStatusText(`오류: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      
      {/* 좌: 캔버스 */}
      <div ref={leftPanelRef} style={{ position: 'absolute', top: 0, left:0, left:0, right: 280, bottom: 0, padding: 16, paddingTop: 68, boxSizing: 'border-box', }}>
        <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: 52, padding: '0 16px', boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 8, zIndex: 20, background: 'var(--bg)', borderBottom: '1px solid var(--border)',}}>
          <button className="btn btn-ghost" onClick={onClose}>← 뒤로</button>
          <span style={{ fontWeight: 600 }}>🖌️ 인페인팅</span>
          <button className="btn btn-ghost" onClick={clearMask} style={{ marginLeft: 'auto' }}>마스크 초기화</button>
        </div>
        <div ref={canvasViewportRef} onMouseDown={handleMouseDown} onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp} style={{ position: 'absolute', top:52, left: 16, right: 16, right: 16, bottom: 16, overflow: 'hidden', }}>
          <div ref={canvasStageRef} style={{ position: 'absolute', left:0, top:0, transformOrigin: '0 0', transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`, }}>
            {/* 베이스 이미지 캔버스 */}
            <canvas ref={canvasRef} style={{ display: 'block', borderRadius: 8 }} />
            {/* 마스크 드로잉 캔버스 (오버레이) */}
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
          {(running || progress > 0) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: `${progress * 100}%` }} />
              </div>
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{statusText}</span>
            </div>
          )}
      </div>
      {/* 우: 설정 패널 */}
      <div style={{ position: 'absolute', top: 0, right: 0, right: 0, bottom:0, width: 280, boxSizing: 'border-box', borderLeft: '1px solid var(--border)', padding: 16, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto', zIndex: 30, }}>

        <div>
          <label>브러시 크기: {brushSize}</label>
          <input type="range" min={5} max={100} value={brushSize}
            onChange={e => setBrushSize(+e.target.value)}
            style={{ padding: 0, border: 'none', background: 'none' }} />
        </div>

        <div>
          <label>인페인팅 모드</label>
          {MODES.map(m => (
            <button key={m} className="btn btn-ghost" style={{ width: '100%', marginBottom: 4, fontSize: 11,
              ...(mode === m ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
              onClick={() => setMode(m)}>{m}</button>
          ))}
        </div>

        <div>
          <label>프롬프트</label>
          <textarea value={prompt} onChange={e => setPrompt(e.target.value)} style={{ height: 80, resize: 'vertical' }} />
        </div>

        <div>
          <label>네거티브</label>
          <textarea value={negative} onChange={e => setNegative(e.target.value)} style={{ height: 60, resize: 'vertical' }} />
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

        <button className="btn btn-primary" onClick={runInpaint} disabled={running} style={{ marginTop: 'auto' }}>
          {running ? '처리 중...' : '✅ 인페인팅 시작'}
        </button>

        {resultSrc && (
          <button className="btn btn-ghost" onClick={onDone}>
            ✅ 완료 (히스토리로 돌아가기)
          </button>
        )}
      </div>
    </div>
  )
}
