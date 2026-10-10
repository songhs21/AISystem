// src/pages/GeneratePage.jsx
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  client,
  sdApi,
  historyApi,
  API_BASE,
  systemApi
} from '../api/client'
import TagPanel from '../components/TagPanel'
import ImageViewer from '../components/ImageViewer'
import Fuse from 'fuse.js'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { dedupeTags, appendTags, appendText } from '../utils/tags'
import QueueStrip, { itemMeta } from '../components/QueueStrip'
import { usePersistentState } from '../hooks/usePersistentState'
import { useDragResize } from '../hooks/useDragResize'
import ResizeHandle from '../components/ResizeHandle'
import { CATEGORY_ORDER, CATEGORY_CONFIG } from '../constants/tagConfig'

// 오른쪽 태그 패널 폭 (뷰포트 밀림 / 패널 / 토글 버튼 위치에 공통 사용)
const DNA_TAB_H = 30                   // 하단 DNA 토글 탭 높이
const OVERLAY_BOTTOM = DNA_TAB_H + 6   // 하단 오버레이가 뷰포트 바닥에서 떨어진 거리
const ANIM = '0.25s ease'
// ─── 유틸 함수 ───────────────────────────────────────────────────
function getByPath(obj, path) {
  return path.split('.').reduce((acc, k) => acc?.[k], obj)
}

function flattenTags(obj, result = []) {
  if (!obj || typeof obj !== 'object') return result
  for (const [key, val] of Object.entries(obj)) {
    if (val && typeof val === 'object' && 'ko' in val && Object.keys(val).length <= 2) {
      result.push({ en: key, ko: val.ko })
    } else if (val && typeof val === 'object') {
      flattenTags(val, result)
    }
  }
  return result
}

function getSubcategoryTags(fileData, subKey) {
  const node = getByPath(fileData, subKey)
  if (!node) return []
  return flattenTags(node)
}

function flattenTagsToMap(obj, map = {}) {
  if (!obj || typeof obj !== 'object') return map
  for (const [key, val] of Object.entries(obj)) {
    if (val && typeof val === 'object' && 'ko' in val && Object.keys(val).length <= 2) {
      map[key] = val.ko
    } else if (val && typeof val === 'object') {
      flattenTagsToMap(val, map)
    }
  }
  return map
}

function buildFuse(list) {
  return new Fuse(list, {
    keys: ['en', 'ko'],
    threshold: 0.4,
    distance: 100,
    includeScore: true,
  })
}

// ─── PromptTags ──────────────────────────────────────────────────
function PromptTags({ prompt }) {
  const tags = (prompt || '').split(',').map(t => t.trim()).filter(Boolean)
  return (
    <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.8, padding: '6px 12px' }}>
      {tags.map((tag, i) => (
        <span key={i} style={{
          display: 'inline-block', margin: '2px 3px', padding: '1px 6px',
          borderRadius: 4, background: 'var(--bg3)', border: '1px solid var(--border)',
        }}>{tag}</span>
      ))}
    </div>
  )
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────────
export default function GeneratePage({ quote }) {
  const [mode, setMode] = useState('T2I')          // 'T2I' | 'I2I' | 'video'
  const imageModeRef = useRef('T2I') // 이미지 탭에서 마지막으로 쓴 서브 모드
  const tab = mode === 'video' ? 'video' : 'image'

  const [checkpoint, setCheckpoint] = usePersistentState('checkpoint', '')
  const [result, setResult] = useState(null)
  const [meta, setMeta] = useState(null)
  const [i2iOverlay, setI2iOverlay] = useState(null)
  const [showHistoryPicker, setShowHistoryPicker] = useState(false)
  const [historyPickerTarget, setHistoryPickerTarget] = useState(null)
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(true)
  const [tagPanelOpen, setTagPanelOpen] = useState(false)
  const [pendingQuote, setPendingQuote] = useState(null)

  // ── 생성 대기열 (서버 큐 폴링) ──
  const [queueOpen, setQueueOpen] = useState(true)
  const [queueActive, setQueueActive] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const followRef = useRef(true)      // 새로 완료된 항목을 자동으로 보여줄지
  const seenDoneRef = useRef(null)    // 이미 확인한 완료 항목 id (null = 첫 로드 전)
  const [dnaOpen, setDnaOpen] = usePersistentState('dnaOpen', true)
  const overlayRef = useRef(null)
  const [overlayH, setOverlayH] = useState(0)
  const [leftW, setLeftW]       = usePersistentState('leftDrawerW', 380)
  const [tagPanelW, setTagPanelW] = usePersistentState('tagPanelW', Math.max(320, Math.round(window.innerWidth * 0.35)))
  const [queueCardSize, setQueueCardSize] = usePersistentState('queueCardSize', 88)
  const [resizing, setResizing] = useState(false)
  const tr = s => (resizing ? 'none' : s)   // 드래그 중에는 전환 애니메이션 끄기

  const leftResize  = useDragResize({ value: leftW,     onChange: setLeftW,     min: 300, max: 720, axis: 'x', dir: 1,  onDragChange: setResizing })
  const rightResize = useDragResize({ value: tagPanelW, onChange: setTagPanelW, min: 280, max: 800, axis: 'x', dir: -1, onDragChange: setResizing })

  useEffect(() => {
    const el = overlayRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setOverlayH(el.offsetHeight))
    ro.observe(el)
    setOverlayH(el.offsetHeight)
    return () => ro.disconnect()
  }, [])

  const dnaRef = useRef(null)
  const [dnaH, setDnaH] = useState(0)

  useEffect(() => {
    const el = dnaRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setDnaH(el.offsetHeight))
    ro.observe(el)
    setDnaH(el.offsetHeight)
    return () => ro.disconnect()
  }, [])

  // DNA 서랍이 열려서 차지하는 높이 (닫히거나 meta 없으면 0)
  const dnaShift = dnaOpen && meta ? dnaH : 0


  const { data: queueData, refetch: refetchQueue } = useQuery({
    queryKey: ['gen-queue'],
    queryFn: () => sdApi.queue().then(r => r.data),
    refetchInterval: queueActive ? 1000 : 5000,
    staleTime: 0,
  })
  const queueItems = queueData?.items || []
  const queryClient = useQueryClient()
  const waitingNo = {}
  {
    let n = 0
    queueItems.forEach(i => { if (i.status === 'waiting') waitingNo[i.id] = ++n })
  }

  const activeItem = queueItems.find(i => i.status === 'running' || i.status === 'cancelling')
  const lastError = [...queueItems].reverse().find(i => i.status === 'error')
  // 시스템 종료
  const shutdown = queueData?.shutdown || { armed: false, remaining: 0 }
  const selectedItem = queueItems.find(i => i.id === selectedId)
  const showRunningCenter = selectedItem && ['waiting', 'running', 'cancelling'].includes(selectedItem.status)


  // 태그 패널 전용 state (드롭박스 결과에만 사용)
  const [tags, setTags] = useState([])
  const [usedPrompt, setUsedPrompt] = useState('')
  const [passType, setPassType] = useState('문제 없음')
  const [likedTags, setLikedTags] = useState(new Set())
  const [dislikedTags, setDislikedTags] = useState(new Set())
  const [falseTags, setFalseTags] = useState(new Set())
  const [score, setScore] = useState(5)

  const { data: cpData, isError: cpError, isFetching: cpFetching, refetch: refetchCp } = useQuery({
    queryKey: ['checkpoints'],
    queryFn: () => sdApi.checkpoints().then(r => r.data),
  })
  const checkpoints = cpData?.checkpoints || []

  useEffect(() => {
    if (!checkpoints.length) return
    // 저장된 값이 없거나 목록에서 사라진 파일이면 첫 번째 모델로
    if (!checkpoint || !checkpoints.includes(checkpoint)) {
      setCheckpoint(checkpoints[0])
    }
  }, [checkpoints])

  const { data: tagFileData = {} } = useQuery({
    queryKey: ['tag-file-data'],
    queryFn: async () => {
      const results = {}
      await Promise.all(
        CATEGORY_ORDER.map(async (cat) => {
          try {
            const filename = cat === 'Attire' ? 'Attire.json' : `${cat}.json`
            const res = await client.get(`/api/system/tags/${filename}`)
            results[cat] = res.data
          } catch { results[cat] = {} }
        })
      )
      return results
    },
    staleTime: Infinity,
  })

  const koMap = useMemo(() => {
    const map = {}
    for (const cat of CATEGORY_ORDER) flattenTagsToMap(tagFileData[cat] || {}, map)
    return map
  }, [tagFileData])

  const allWeights = useQuery({
    queryKey: ['all-tag-weights'],
    queryFn: () => historyApi.allTagWeights().then(r => r.data),
    staleTime: Infinity,
  }).data || {}

  useEffect(() => {
    if (!quote) return
    const target = quote.target || 'T2I'     // 'T2I' | 'I2I' | 'video'
    selectMode(target)
    setLeftDrawerOpen(true)

    if (quote.checkpoint) {
      const base = quote.checkpoint.split(/[/\\]/).pop()
      const match = checkpoints.find(c => c === quote.checkpoint) || checkpoints.find(c => c === base)
      if (match) setCheckpoint(match)
      else alert(`체크포인트를 찾을 수 없음: ${base}`)
    }

    if (quote.positive != null || quote.negative != null) setPendingQuote({ ...quote, target })
  }, [quote])
  
  function openHistoryPicker(onPickCallback) {
    setHistoryPickerTarget(() => onPickCallback)
    setShowHistoryPicker(true)
  }
  // 탭 토글
  function selectTab(t) {
    setMode(t === 'video' ? 'video' : imageModeRef.current)
  }
  function selectMode(m) {
    if (m !== 'video') imageModeRef.current = m
    setMode(m)
  }

  // 좋아요/싫어요/패스 중 하나만 선택되도록 토글 (이미 해당 상태면 해제)
function toggleFeedbackTag(tag, kind) {
  const sets = {
    like:    [likedTags,    setLikedTags],
    dislike: [dislikedTags, setDislikedTags],
    pass:    [falseTags,    setFalseTags],
  }
  const had = sets[kind][0].has(tag)
  Object.values(sets).forEach(([, set]) =>
    set(prev => { const s = new Set(prev); s.delete(tag); return s })
  )
  if (!had) sets[kind][1](prev => new Set(prev).add(tag))
}

  async function saveFeedback() {
    if (!result) return
    await historyApi.saveFeedback({
      generation_id: result.gen_id,
      score: passType === '마음에 들지 않음' ? null : score,
      liked_tags: [...likedTags],
      disliked_tags: [...dislikedTags],
      false_tags: [...falseTags],
      pass_type: { '문제 없음': null, '그림체': 'style', '인체 디테일': 'quality', '마음에 들지 않음': 'dislike' }[passType],
      pass_reasons: [],
    })
    setResult(null)
    setTags([])
    setTagPanelOpen(false)
    setSelectedId(null)
  }

  useEffect(() => {
    setQueueActive(
      queueItems.some(i => ['waiting', 'running', 'cancelling'].includes(i.status)) ||
      (queueData?.shutdown?.remaining ?? 0) > 0 ||
      !!queueData?.shutdown?.extracting
    )
  }, [queueData])

  async function showItem(item) {
    setSelectedId(item.id)
    setMeta(itemMeta(item))
    setLikedTags(new Set()); setDislikedTags(new Set()); setFalseTags(new Set())
    setScore(5); setPassType('문제 없음')
    const r = item.result || {}

    if (item.kind === 'i2v') {
      setResult({ video_path: r.video_path, isVideo: true })
      setTags([]); setUsedPrompt(''); setTagPanelOpen(false)
    } else if (item.kind === 'i2i') {
      setResult({ image_path: r.image_path })
      setTags([]); setUsedPrompt(''); setTagPanelOpen(false)
    } else {
      setResult({ gen_id: r.gen_id, image_path: r.image_path })
      try {
        const gen = await historyApi.generation(r.gen_id)
        setUsedPrompt(gen.data.prompt || '')
        setTags(gen.data.tags || [])
        setTagPanelOpen(true)
      } catch (e) { console.error('태그 조회 실패:', e) }
    }
  }

  // 새로 완료된 항목 자동 표시 (보던 항목이 최신이 아니면 건너뜀)
  useEffect(() => {
    const done = queueItems.filter(i => i.status === 'done')
    if (seenDoneRef.current === null) {
      seenDoneRef.current = new Set(done.map(i => i.id))   // 첫 로드 때 기존 완료분은 자동 표시하지 않음
      return
    }
    const fresh = done.filter(i => !seenDoneRef.current.has(i.id))
    if (!fresh.length) return
    fresh.forEach(i => seenDoneRef.current.add(i.id))
    if (followRef.current) showItem(fresh[fresh.length - 1])
  }, [queueData])

  function enqueueErrorMessage(e) {
    if (e.code === 'ECONNABORTED' || e.code === 'ETIMEDOUT')
      return '서버 응답이 없습니다. 대기열을 확인한 뒤 다시 시도해 주세요.'
    if (!e.response)
      return '네트워크 오류로 생성 요청을 보내지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.'
    const detail = e.response.data?.detail
    if (Array.isArray(detail))      // FastAPI 검증 오류: [{loc, msg}, ...]
      return detail.map(d => d?.msg || JSON.stringify(d)).join('\n')
    if (typeof detail === 'string' && detail) return detail
    return e.message
  }

  async function enqueue(request) {
    try {
      await request()
    } catch (e) {
      alert(enqueueErrorMessage(e))
      return
    }
    await refetchQueue()
  }

  function startI2v(payload) {
    return enqueue(() => sdApi.enqueueI2v(payload))
  }

    function handleSelect(item) {
    if (['waiting', 'running', 'cancelling'].includes(item.status)) {
      followRef.current = true   // 이 항목이 끝나면 자동으로 결과를 보여줌
      setSelectedId(item.id)
      setMeta(itemMeta(item))
      setResult(null)
      setTags([]); setUsedPrompt(''); setTagPanelOpen(false)
      return
    }
    const latestDone = [...queueItems].reverse().find(i => i.status === 'done')
    followRef.current = latestDone?.id === item.id
    showItem(item)
  }

  async function handleReorder(ids) {
    queryClient.setQueryData(['gen-queue'], old => {
      if (!old) return old
      const byId = Object.fromEntries(old.items.map(i => [i.id, i]))
      const queue = ids.map(id => byId[id]).filter(i => i?.status === 'waiting')
      let k = 0
      return { ...old, items: old.items.map(i => (i.status === 'waiting' ? queue[k++] ?? i : i)) }
    })
    await sdApi.reorderQueue(ids).catch(() => {})
    refetchQueue()
  }

  async function handleRemove(item) {
    await sdApi.removeQueueItem(item.id).catch(() => {})
    refetchQueue()
  }

  async function handleClearPending() {
    if (!confirm('대기 중인 항목과 진행 중인 작업을 모두 취소할까요?')) return
    await sdApi.clearQueue().catch(() => {})
    refetchQueue()
  }
  // 시스템 종료 핸들러
  async function handleToggleShutdown() {
    if (!shutdown.armed &&
        !confirm('대기열의 모든 작업이 끝나면 PC를 종료합니다.\n(종료 60초 전부터 취소할 수 있습니다) 설정할까요?')) return
    await sdApi.setQueueShutdown(!shutdown.armed).catch(() => {})
    refetchQueue()
  }

  async function handleAbortShutdown() {
    await sdApi.abortQueueShutdown().catch(() => {})
    refetchQueue()
  }

  const isVideo = result?.isVideo
  const hasTags = tags.length > 0
  const generateRef = useRef(null)
  const [canGenerate, setCanGenerate] = useState(false)
  const bindGenerate = useCallback((fn, enabled) => {
    generateRef.current = fn
    setCanGenerate(prev => (prev === enabled ? prev : enabled))
  }, [])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', overflow: 'hidden' }}>

      <QueueStrip
        items={queueItems}
        open={queueOpen}
        onToggle={() => setQueueOpen(v => !v)}
        selectedId={selectedId}
        onSelect={handleSelect}
        onRemove={handleRemove}
        onClearPending={handleClearPending}
        shutdown={shutdown}
        onToggleShutdown={handleToggleShutdown}
        onAbortShutdown={handleAbortShutdown}
        cardSize={queueCardSize}
        onCardSizeChange={setQueueCardSize}
        onReorder={handleReorder}
      />

      {/* 뷰포트 + 서랍 영역 */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden', paddingTop: 10 }}>

      {/* 뷰포트 (오른쪽 태그 패널이 열리면 밀림) — 이미지는 이 영역 전체를 사용 */}
        <div style={{
          position: 'absolute', inset: 0,
          right: tagPanelOpen ? tagPanelW : 0,
          transition: tr(`right ${ANIM}`),
          overflow: 'hidden',
          background: 'var(--bg2)',
        }}>
          {/* 이미지 / 영상: 중앙 패널 전 영역 */}
          <div style={{
            position: 'absolute', inset: 0,
            padding: `5px 5px ${overlayH + dnaShift + OVERLAY_BOTTOM + 5}px 5px`,
            transition: `padding ${ANIM}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {result ? (
              isVideo
                ? <video src={`${API_BASE}/api/system/video?path=${encodeURIComponent(result.video_path)}`}
                    controls autoPlay loop
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                : <ImageViewer
                    src={`${API_BASE}/api/system/image?path=${encodeURIComponent(result.image_path)}`}
                    style={{ width: '100%', height: '100%' }} />
            ) : showRunningCenter ? (
              selectedItem.status === 'waiting' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                  <div style={{ fontSize: 14 }}>[{selectedItem.kind}] 대기 #{waitingNo[selectedItem.id]}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>앞선 작업이 끝나면 시작됩니다</div>
                </div>
              ) : (
                <div style={{ width: 'min(360px, 80%)', display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'center' }}>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>[{selectedItem.kind}] 생성 중</div>
                  <div className="progress-bar" style={{ height: 10 }}>
                    <div className="progress-bar-fill" style={{ width: `${(selectedItem.progress || 0) * 100}%` }} />
                  </div>
                  <div style={{ fontSize: 12 }}>
                    {Math.round((selectedItem.progress || 0) * 100)}% · {selectedItem.status === 'cancelling' ? '취소 중...' : selectedItem.text}
                  </div>
                </div>
              )
            ) : (
              <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>
                생성된 결과가 여기에 표시됩니다
              </div>
            )}
          </div>

          {/* 하단 오버레이: 진행률 / 에러 / 메타 (이미지 드래그를 가로막지 않도록 pointerEvents 분리) */}
          <div
            ref={overlayRef}
            style={{
              position: 'absolute', bottom: OVERLAY_BOTTOM, right: 16,
              left: leftDrawerOpen ? leftW + 16 : 16,
              transition: tr(`bottom ${ANIM}, left ${ANIM}`),
              zIndex: 5,
              display: 'flex', flexDirection: 'column', gap: 6,
              pointerEvents: 'none',
            }}
          >
            {/* 프로그레스(70) + 생성 버튼(30) */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
              <div style={{ flex: 7, minWidth: 0 }}>
                <div style={{
                  display: 'flex', flexDirection: 'column', gap: 4,
                  padding: '6px 10px', borderRadius: 8,
                  background: 'rgba(36,36,36,0.85)', border: '1px solid var(--border)',
                }}>
                  <div className="progress-bar">
                    <div className="progress-bar-fill" style={{ width: `${(activeItem?.progress || 0) * 100}%` }} />
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                    {activeItem
                      ? `[${activeItem.kind}] ${activeItem.status === 'cancelling' ? '취소 중...' : activeItem.text}`
                      : '대기 중'}
                  </span>
                </div>
              </div>

              <div style={{ flex: 3, minWidth: 0, display: 'flex', pointerEvents: 'auto' }}>
                <button
                  className="btn btn-primary"
                  disabled={!canGenerate}
                  onClick={() => generateRef.current?.()}
                  style={{ flex: 1, padding: '8px 12px', fontSize: 13, whiteSpace: 'nowrap' }}
                >
                  {tab === 'video' ? '🎬 영상 생성' : '🖼️ 이미지 생성'}
                </button>
              </div>
            </div>

            {lastError && (
              <div style={{
                color: 'var(--danger)', fontSize: 12,
                padding: '6px 10px', borderRadius: 8,
                background: 'rgba(36,36,36,0.85)', border: '1px solid var(--border)',
              }}>⚠ [{lastError.kind}] {lastError.error}</div>
            )}

          </div>
        </div>

        {/* 왼쪽 서랍 토글 버튼 (파일탭 형태) */}
        <button
          onClick={() => setLeftDrawerOpen(v => !v)}
          style={{
            position: 'absolute', top: 0,
            left: leftDrawerOpen ? leftW : 0,
            zIndex: 60,
            width: 60, height: 60,
            border: '1px solid var(--border)', borderTop: 'none', borderLeft: leftDrawerOpen ? 'none' : undefined,
            borderRadius: '0 0 12px 0',
            background: 'var(--bg2)', color: 'var(--text-dim)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, cursor: 'pointer',
            transition: tr(`left ${ANIM}`),
          }}
        >
          {leftDrawerOpen ? '◀ 접기' : '옵션 ▶'}
        </button>

        {/* 왼쪽 서랍: 화면 왼쪽 바깥에서 밀고 들어옴 (언마운트하지 않고 transform으로만 숨김) */}
        <div style={{
          position: 'absolute', top: 0, left: 0, bottom: 0, zIndex: 50,
          width: leftW, maxWidth: '90vw',
          background: 'var(--bg2)', borderRight: '1px solid var(--border)',
          boxShadow: leftDrawerOpen ? '4px 0 16px rgba(0,0,0,0.3)' : 'none',
          display: 'flex', flexDirection: 'column',
          paddingTop: 16,
          transform: leftDrawerOpen ? 'translateX(0)' : 'translateX(-100%)',
          visibility: leftDrawerOpen ? 'visible' : 'hidden',
          transition: tr(leftDrawerOpen
            ? `transform ${ANIM}, visibility 0s`
            : `transform ${ANIM}, visibility 0s linear 0.25s`),
        }}>
          <ResizeHandle axis="x" style={{ right: 0 }} {...leftResize} onDoubleClick={() => setLeftW(380)} />
        
          {/* 탭 전환 */}
          <div style={{ display: 'flex', gap: 4, padding: '0 12px 6px' }}>
            {[['image', '🖼️ 이미지'], ['video', '🎬 영상']].map(([key, label]) => (
              <button key={key} className="btn btn-ghost"
                style={{ fontSize: 12, padding: '4px 12px', ...(tab === key ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                onClick={() => selectTab(key)}>
                {label}
              </button>
            ))}
          </div>
          {tab === 'image' && (
            <div style={{ display: 'flex', gap: 4, padding: '0 12px 10px' }}>
              {[['T2I', 'T2I'], ['I2I', 'I2I']].map(([key, label]) => (
                <button key={key} className="btn btn-ghost"
                  style={{ fontSize: 11, padding: '3px 10px', ...(mode === key ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                  onClick={() => selectMode(key)}>
                  {label}
                </button>
              ))}
            </div>
          )}

          {mode !== 'video' && (
            <div style={{ padding: '0 12px 10px' }}>
              <label>체크포인트</label>
              <select value={checkpoint} onChange={e => setCheckpoint(e.target.value)}>
                {checkpoints.map(c => <option key={c}>{c}</option>)}
              </select>
              <ListStatus
                error={cpError}
                empty={!cpError && !cpFetching && checkpoints.length === 0}
                fetching={cpFetching}
                onRetry={refetchCp}
                errorText="체크포인트 목록을 불러오지 못했습니다."
                emptyText="체크포인트가 없습니다. 설치 폴더/models/checkpoints 에 모델 파일을 옮긴 뒤 다시 시도하세요."
              />
            </div>
          )}

          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', padding: '0 12px 12px' }}>
            {mode === 'T2I' && (
              <T2iModePanel
                checkpoint={checkpoint}
                tagFileData={tagFileData}
                allWeights={allWeights}
                onEnqueue={enqueue}
                bindGenerate={bindGenerate}
                pendingQuote={pendingQuote}
                onQuoteConsumed={() => setPendingQuote(null)}
              />
            )}
            {mode === 'I2I' && (
              <I2iModePanel
                checkpoint={checkpoint}
                onEnqueue={enqueue}
                bindGenerate={bindGenerate}
                onPreview={src => setI2iOverlay(src)}
                openHistoryPicker={openHistoryPicker}
                pendingQuote={pendingQuote}
                onQuoteConsumed={() => setPendingQuote(null)}
              />
            )}
            {mode === 'video' && (
              <VideoModePanel
                onRun={startI2v}
                bindGenerate={bindGenerate}
                onPreview={src => setI2iOverlay(src)}
                openHistoryPicker={openHistoryPicker}
                pendingQuote={pendingQuote}
                onQuoteConsumed={() => setPendingQuote(null)}
              />
            )}
          </div>
        </div>


        {/* 오른쪽 태그 패널 (뷰포트를 밀어냄, 닫으면 완전히 숨김 — 언마운트 방지로 display 토글) */}
        {hasTags && (
          <button
            onClick={() => setTagPanelOpen(v => !v)}
            style={{
              position: 'absolute', top: 0,
              right: tagPanelOpen ? tagPanelW : 0,
              zIndex: 60,
              width: 60, height: 60,
              border: '1px solid var(--border)', borderTop: 'none',
              borderRight: tagPanelOpen ? 'none' : undefined,
              borderRadius: '0 0 0 12px',
              background: 'var(--bg2)', color: 'var(--text-dim)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, cursor: 'pointer',
              transition: tr(`right ${ANIM}`),
            }}
          >
            {tagPanelOpen ? '▶' : '◀'}
          </button>
        )}

        {hasTags && (
          <div style={{
            position: 'absolute', top: 0, right: 0, bottom: 0,
            width: tagPanelW,
            background: 'var(--bg2)', borderLeft: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column', overflow: 'hidden',
            zIndex: 40,
            boxShadow: tagPanelOpen ? '-4px 0 16px rgba(0,0,0,0.3)' : 'none',
            transform: tagPanelOpen ? 'translateX(0)' : 'translateX(100%)',
            visibility: tagPanelOpen ? 'visible' : 'hidden',
            transition: tr(tagPanelOpen
              ? `transform ${ANIM}, visibility 0s`
              : `transform ${ANIM}, visibility 0s linear 0.25s`),
          }}>
            <ResizeHandle axis="x" style={{ left: 0 }} {...rightResize}
              onDoubleClick={() => setTagPanelW(Math.max(320, Math.round(window.innerWidth * 0.35)))} />
            {/* 헤더 */}
            <div style={{
              padding: '10px 14px', borderBottom: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
            }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>🏷️ 태그 피드백</span>
              {result?.gen_id != null && (
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>#{result.gen_id}</span>
              )}
            </div>

            {/* 사용된 프롬프트 */}
            <div style={{ maxHeight: 110, overflowY: 'auto', flexShrink: 0 }}>
              <PromptTags prompt={usedPrompt} />
            </div>

            {/* 패스 유형 */}
            <div style={{
              padding: '8px 14px', borderBottom: '1px solid var(--border)',
              display: 'flex', gap: 4, flexWrap: 'wrap', flexShrink: 0,
            }}>
              {['문제 없음', '그림체', '인체 디테일', '마음에 들지 않음'].map(p => (
                <button key={p} className="btn btn-ghost"
                  style={{ fontSize: 11, padding: '3px 8px',
                    ...(passType === p ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                  onClick={() => setPassType(p)}
                >{p}</button>
              ))}
            </div>

            {/* 태그 목록 */}
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
              {passType !== '마음에 들지 않음' && (
                <TagPanel
                  tags={tags}
                  liked={likedTags} disliked={dislikedTags} passed={falseTags}
                  onLike={tag => toggleFeedbackTag(tag, 'like')}
                  onDislike={tag => toggleFeedbackTag(tag, 'dislike')}
                  onPass={tag => toggleFeedbackTag(tag, 'pass')}
                />
              )}
            </div>

            {/* 스코어 */}
            {passType !== '마음에 들지 않음' && (
              <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
                <label>Score: {score}</label>
                <input type="range" min={0} max={10} value={score}
                  onChange={e => setScore(+e.target.value)}
                  style={{ width: '100%', padding: 0, border: 'none', background: 'none' }} />
              </div>
            )}

            {/* 저장 */}
            <div style={{ padding: 12, borderTop: '1px solid var(--border)', flexShrink: 0 }}>
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={saveFeedback}>
                피드백 저장
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 공용 오버레이들 */}
      {i2iOverlay && (
        <div onClick={() => setI2iOverlay(null)} style={{ position: 'fixed', inset: 0, zIndex: 400, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src={i2iOverlay} style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8 }} />
        </div>
      )}
      {showHistoryPicker && (
        <HistoryImagePicker
          onPick={(gen) => { historyPickerTarget?.(gen); setShowHistoryPicker(false) }}
          onClose={() => setShowHistoryPicker(false)}
        />
      )}
      {/* DNA 서랍: 화면 아래 바깥에서 올라오고 내려감 */}
      <div
        ref={dnaRef}
        style={{
          position: 'absolute', bottom: 0, right: 16,
          left: leftDrawerOpen ? 396 : 16,
          paddingBottom: 6,
          zIndex: 5,
          transform: dnaOpen ? 'translateY(0)' : 'translateY(100%)',
          transition: `transform ${ANIM}, left 0.2s ease`,
          pointerEvents: 'none',
        }}
      >
        {meta && (
          <div style={{
            background: 'rgba(36,36,36,0.85)', border: '1px solid var(--border)',
            borderRadius: 8, padding: 10, fontSize: 11, color: 'var(--text-dim)',
            maxHeight: 100, overflow: 'auto',
            pointerEvents: dnaOpen ? 'auto' : 'none',
          }}>
            {Object.entries(meta).map(([k, v]) => (
              v !== undefined && v !== '' && (
                <span key={k} style={{ marginRight: 12 }}>
                  <span style={{ color: 'var(--text)' }}>{k}</span>: {String(v)}
                </span>
              )
            ))}
          </div>
        )}
      </div>

      {/* DNA 토글 탭: 서랍 윗변에 붙어 같이 움직임 */}
      <button
        onClick={() => setDnaOpen(v => !v)}
        style={{
          position: 'absolute', left: '50%', transform: 'translateX(-50%)',
          bottom: dnaShift,
          transition: `bottom ${ANIM}`,
          width: 100, height: DNA_TAB_H, zIndex: 6,
          border: '1px solid var(--border)', borderBottom: 'none', borderRadius: '12px 12px 0 0',
          background: 'var(--bg2)', color: 'var(--text-dim)', fontSize: 12, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
        }}
      >
        {dnaOpen ? '▼' : '▲'} DNA
      </button>
    </div>
  )
}

// ── 공용 슬롯 컴포넌트 ─────────────────────────────────────
function I2iSlot({ label, required, value, onUpload, onHistoryPick, onDraw, onRemove, onPreview }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 8px', borderRadius: 6,
      background: 'var(--bg3)', border: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 11, color: 'var(--text-dim)', minWidth: 52 }}>
        {label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}
      </span>

      {value ? (
        <>
          <img
            src={value.src}
            onClick={() => onPreview(value.src)}
            style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4, cursor: 'pointer', border: '1px solid var(--border)' }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-dim)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {value.filename}
          </span>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 6px' }} onClick={onRemove}>×</button>
        </>
      ) : (
        <>
          {onDraw ? (
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={onDraw}>
              🖌️ 드로잉
            </button>
          ) : (
            <label style={{ margin: 0 }}>
              <input type="file" accept="image/*" onChange={onUpload} style={{ display: 'none' }} />
              <span className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px', cursor: 'pointer' }}>📁 업로드</span>
            </label>
          )}
          {onHistoryPick && (
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }} onClick={onHistoryPick}>
              📋 히스토리
            </button>
          )}
        </>
      )}
    </div>
  )
}

// ── 히스토리 이미지 피커 ──────────────────────────────────
function HistoryImagePicker({ onPick, onClose }) {
  const { data: gensData } = useQuery({
    queryKey: ['generations'],
    queryFn: () => historyApi.generations().then(r => r.data),
  })
  const generations = (gensData?.generations || []).filter(g => g.media_type !== 'video')

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
            const path = gen.image_path
            const src = `${API_BASE}/api/system/image?path=${encodeURIComponent(path)}`
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

// ── 마스크 드로잉 오버레이 ────────────────────────────────
function MaskDrawOverlay({ imageSrc, onDone, onClose }) {
  const canvasRef    = useRef(null)
  const maskRef      = useRef(null)
  const viewportRef  = useRef(null)
  const stageRef     = useRef(null)
  const [brushSize, setBrushSize] = useState(30)
  const [drawing, setDrawing]     = useState(false)
  const [zoom, setZoom]           = useState(1)
  const [offset, setOffset]       = useState({ x: 0, y: 0 })
  const panStartRef  = useRef(null)
  const [panning, setPanning]     = useState(false)

  useEffect(() => {
    const img = new Image()
    img.onload = () => {
      const canvas = canvasRef.current
      const mask   = maskRef.current
      const viewport = viewportRef.current
      if (!canvas || !mask || !viewport) return

      canvas.width  = img.naturalWidth
      canvas.height = img.naturalHeight
      mask.width    = img.naturalWidth
      mask.height   = img.naturalHeight

      const vw = viewport.clientWidth
      const vh = viewport.clientHeight
      const scale = Math.min((vw * 0.9) / img.naturalWidth, (vh * 0.9) / img.naturalHeight)

      const displayW = img.naturalWidth  * scale
      const displayH = img.naturalHeight * scale

      canvas.style.width  = `${displayW}px`
      canvas.style.height = `${displayH}px`
      mask.style.width    = `${displayW}px`
      mask.style.height   = `${displayH}px`

      canvas.getContext('2d').drawImage(img, 0, 0)
      setOffset({ x: (vw - displayW) / 2, y: (vh - displayH) / 2 })
      setZoom(1)
    }
    img.src = imageSrc
  }, [imageSrc])

  const handleWheel = useCallback((e) => {
    e.preventDefault()
    const viewport = viewportRef.current
    const stage    = stageRef.current
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
    const el = viewportRef.current
    if (!el) return
    el.addEventListener('wheel', handleWheel, { passive: false })
    return () => el.removeEventListener('wheel', handleWheel)
  }, [handleWheel])

  function getPos(e) {
    const rect   = maskRef.current.getBoundingClientRect()
    const scaleX = maskRef.current.width  / rect.width
    const scaleY = maskRef.current.height / rect.height
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top)  * scaleY,
    }
  }

  function draw(e) {
    if (!drawing || e.buttons !== 1) return
    const { x, y } = getPos(e)
    const ctx = maskRef.current.getContext('2d')
    ctx.fillStyle = 'rgba(255, 0, 0, 0.5)'
    ctx.beginPath()
    ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2)
    ctx.fill()
  }

  function handleMouseDown(e) {
    if (e.button === 1) {
      e.preventDefault()
      setPanning(true)
      panStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, offsetX: offset.x, offsetY: offset.y }
    }
  }

  function handleMouseMove(e) {
    if (panning && panStartRef.current) {
      const s = panStartRef.current
      setOffset({ x: s.offsetX + (e.clientX - s.mouseX), y: s.offsetY + (e.clientY - s.mouseY) })
    }
  }

  function handleMouseUp(e) {
    if (e.button === 1) { setPanning(false); panStartRef.current = null }
  }

  function clearMask() {
    const ctx = maskRef.current.getContext('2d')
    ctx.clearRect(0, 0, maskRef.current.width, maskRef.current.height)
  }

  function handleDone() {
    const tmp = document.createElement('canvas')
    tmp.width  = maskRef.current.width
    tmp.height = maskRef.current.height
    const ctx  = tmp.getContext('2d')
    ctx.drawImage(maskRef.current, 0, 0)
    const imageData = ctx.getImageData(0, 0, tmp.width, tmp.height)
    const d = imageData.data
    for (let i = 0; i < d.length; i += 4) {
      const hasColor = d[i] > 50 || d[i+1] > 50 || d[i+2] > 50
      d[i] = d[i+1] = d[i+2] = hasColor ? 255 : 0
      d[i+3] = 255
    }
    ctx.putImageData(imageData, 0, 0)
    tmp.toBlob(blob => onDone(blob, tmp.toDataURL()), 'image/png')
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 500,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          display: 'flex', flexDirection: 'column',
          background: 'var(--bg2)', borderRadius: 10,
          border: '1px solid var(--border)',
          overflow: 'hidden',
          width: '90vw', height: '90vh',
        }}
      >
        <div style={{
          height: 48, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 12,
          borderBottom: '1px solid var(--border)', flexShrink: 0,
        }}>
          <span style={{ fontWeight: 600 }}>🎭 마스크 드로잉</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 16 }}>
            <label style={{ margin: 0 }}>브러시: {brushSize}</label>
            <input type="range" min={5} max={100} value={brushSize}
              onChange={e => setBrushSize(+e.target.value)}
              style={{ width: 100, padding: 0, border: 'none', background: 'none' }} />
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 8 }}>휠: 줌 / 중클릭: 패닝</span>
          <button className="btn btn-ghost" style={{ marginLeft: 'auto' }} onClick={clearMask}>초기화</button>
          <button className="btn btn-primary" onClick={handleDone}>완료</button>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div
          ref={viewportRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ flex: 1, position: 'relative', overflow: 'hidden' }}
        >
          <div
            ref={stageRef}
            style={{
              position: 'absolute', left: 0, top: 0,
              transformOrigin: '0 0',
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
            }}
          >
            <canvas ref={canvasRef} style={{ display: 'block' }} />
            <canvas ref={maskRef}
              style={{ position: 'absolute', top: 0, left: 0, cursor: 'crosshair' }}
              onMouseDown={e => { if (e.button === 0) setDrawing(true) }}
              onMouseMove={draw}
              onMouseUp={e => { if (e.button === 0) setDrawing(false) }}
              onMouseLeave={() => setDrawing(false)}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 비디오 모드 패널 ──────────────────────────────────────
function loadI2vDraft() {
  try { return JSON.parse(localStorage.getItem('i2vDraft')) || {} } catch { return {} }
}

function VideoModePanel({ onRun, onPreview, openHistoryPicker, bindGenerate, pendingQuote, onQuoteConsumed }) {
  const [draft] = useState(loadI2vDraft)
  const [subMode, setSubMode]       = useState('i2v')
  const [baseImage, setBaseImage]   = useState(() =>
    draft.baseImage
      ? { ...draft.baseImage, src: `${API_BASE}/api/system/image?path=${encodeURIComponent(draft.baseImage.path)}` }
      : null
  )
  const [prompt, setPrompt]         = useState(draft.prompt ?? '')
  const [negative, setNegative]     = useState(draft.negative ?? '')
  const [seed, setSeed]             = useState(draft.seed ?? -1)
  const [width, setWidth]           = useState(draft.width ?? 1280)
  const [height, setHeight]         = useState(draft.height ?? 720)
  const [length, setLength]         = useState(draft.length ?? 81)
  const [highSteps, setHighSteps]   = useState(draft.highSteps ?? 2)
  const [lowSteps, setLowSteps]     = useState(draft.lowSteps ?? 3)
  const [cfg, setCfg]               = useState(draft.cfg ?? 1.0)
  const [loraName, setLoraName]         = useState(draft.loraName ?? '')
  const [loraStrength, setLoraStrength] = useState(draft.loraStrength ?? 0.8)

  const { data: loraData, isError: loraError, isFetching: loraFetching, refetch: refetchLora } = useQuery({
    queryKey: ['loras'],
    queryFn: () => sdApi.loras().then(r => r.data),
  })
  const loras = loraData?.loras || []

  const lastQuoteRef = useRef(null)

  useEffect(() => {
    if (!pendingQuote) return
    console.log('[quote] video apply', pendingQuote)
    if (pendingQuote.nonce != null && lastQuoteRef.current === pendingQuote.nonce) {
      onQuoteConsumed?.()
      return
    }
    lastQuoteRef.current = pendingQuote.nonce ?? null
    const append = !!pendingQuote.append

    if (pendingQuote.positive != null) {
      setPrompt(prev => append ? appendText(prev, pendingQuote.positive) : pendingQuote.positive)
    }
    if (pendingQuote.negative != null) {
      setNegative(prev => append ? appendText(prev, pendingQuote.negative) : pendingQuote.negative)
    }
    onQuoteConsumed?.()
  }, [pendingQuote])

  // 입력 저장 (변경 시마다)
  useEffect(() => {
    const draft = {
      baseImage: baseImage ? { path: baseImage.path, filename: baseImage.filename } : null,
      prompt, negative, seed, width, height, length, highSteps, lowSteps, cfg, loraName, loraStrength,
    }
    localStorage.setItem('i2vDraft', JSON.stringify(draft))
  }, [baseImage, prompt, negative, seed, width, height, length, highSteps, lowSteps, cfg, loraName, loraStrength])

  useEffect(() => {
    if (!pendingQuote) return
    if (pendingQuote.positive != null) setPrompt(pendingQuote.positive)
    if (pendingQuote.negative != null) setNegative(pendingQuote.negative)
    onQuoteConsumed?.()
  }, [pendingQuote])

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const res = await systemApi.uploadImage(file)
    const src = URL.createObjectURL(file)
    setBaseImage({ path: res.data.path, src, filename: file.name })
  }

  function handleRun() {
    const payload = {
      image_path: baseImage.path, prompt, negative, seed, width, height, length,
      high_steps: highSteps, low_steps: lowSteps, cfg,
      lora_name: loraName, lora_strength: loraStrength,
    }
    const metaInfo = {
      모드: 'I2V', 프롬프트: prompt, 네거티브: negative, 시드: seed,
      해상도: `${width}x${height}`, 프레임: length,
      스텝: `High ${highSteps} / Low ${lowSteps}`, CFG: cfg,
      LoRA: loraName ? `${loraName} (${loraStrength})` : '없음',
    }
    onRun(payload, metaInfo)
  }
  useEffect(() => { bindGenerate?.(handleRun, !!baseImage) })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto', width: '100%' }}>
      {/* 서브 모드 */}
      <div style={{ display: 'flex', gap: 4 }}>
        {[['i2v', '🖼️→🎬 I2V'], ['t2v', '📝→🎬 T2V (준비중)']].map(([key, label]) => (
          <button key={key} className="btn btn-ghost"
            disabled={key === 't2v'}
            style={{ fontSize: 11, padding: '3px 10px', ...(subMode === key ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
            onClick={() => setSubMode(key)}>
            {label}
          </button>
        ))}
      </div>

      {subMode === 'i2v' && (
        <>
          <I2iSlot
            label="베이스"
            required
            value={baseImage}
            onUpload={handleUpload}
            onHistoryPick={() => openHistoryPicker(gen => {
              const path = gen.image_path
              const src = `${API_BASE}/api/system/image?path=${encodeURIComponent(path)}`
              setBaseImage({ path, src, filename: path.split(/[/\\]/).pop() })
            })}
            onRemove={() => setBaseImage(null)}
            onPreview={onPreview}
          />

          <div>
            <label>✅ 프롬프트</label>
            <ClearableTextarea value={prompt} onChange={setPrompt}
              style={{ height: 70, resize: 'vertical', fontSize: 11 }} />
          </div>
          <div>
            <label>❌ 네거티브</label>
            <ClearableTextarea value={negative} onChange={setNegative}
              style={{ height: 50, resize: 'vertical', fontSize: 11 }} />
          </div>

          {/* LoRA */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>🎨 LoRA</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <select value={loraName} onChange={e => setLoraName(e.target.value)} style={{ fontSize: 12 }}>
                <option value="">LoRA 없음</option>
                {loras.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
              <ListStatus
                error={loraError}
                empty={!loraError && !loraFetching && loras.length === 0}
                fetching={loraFetching}
                onRetry={refetchLora}
                errorText="LoRA 목록을 불러오지 못했습니다."
                emptyText="LoRA 파일이 없습니다. 설치 폴더/models/LoRAS 에 모델 파일을 옮긴 뒤 다시 시도하세요."
              />
              {loraName && (
                <>
                  <label>Strength: {loraStrength}</label>
                  <input type="range" min={0} max={1} step={0.05} value={loraStrength}
                    onChange={e => setLoraStrength(+e.target.value)}
                    style={{ padding: 0, border: 'none', background: 'none' }} />
                </>
              )}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div><label>Width</label><input type="number" value={width} step={8} onChange={e => setWidth(+e.target.value)} /></div>
            <div><label>Height</label><input type="number" value={height} step={8} onChange={e => setHeight(+e.target.value)} /></div>
            <div><label>Frames</label><input type="number" value={length} onChange={e => setLength(+e.target.value)} /></div>
            <div><label>Seed (-1=랜덤)</label><input type="number" value={seed} onChange={e => setSeed(+e.target.value)} /></div>
            <div><label>High Steps</label><input type="number" value={highSteps} min={1} onChange={e => setHighSteps(+e.target.value)} /></div>
            <div><label>Low Steps</label><input type="number" value={lowSteps} min={1} onChange={e => setLowSteps(+e.target.value)} /></div>
            <div><label>CFG: {cfg}</label><input type="range" min={1} max={10} step={0.5} value={cfg} onChange={e => setCfg(+e.target.value)} style={{ padding: 0, border: 'none', background: 'none' }} /></div>
          </div>
        </>
      )}
    </div>
  )
}

// ── i2i 모드 패널 ──────────────────────────────────────────
function I2iModePanel({ checkpoint, onEnqueue, onPreview, openHistoryPicker, bindGenerate, pendingQuote, onQuoteConsumed }) {
  const [baseImage, setBaseImage] = useState(null)
  const [maskBlob, setMaskBlob]   = useState(null)
  const [maskSrc, setMaskSrc]     = useState(null)
  const [refImage, setRefImage]   = useState(null)
  const [prompt, setPrompt]       = useState('')
  const [negative, setNegative]   = useState('')
  const [denoise, setDenoise]     = useState(0.7)
  const [seed, setSeed]           = useState(-1)
  const [showMaskDraw, setShowMaskDraw] = useState(false)
  const [loraName, setLoraName]         = useState('')
  const [loraStrength, setLoraStrength] = useState(0.8)

  const { data: loraData, isError: loraError, isFetching: loraFetching, refetch: refetchLora } = useQuery({
    queryKey: ['loras'],
    queryFn: () => sdApi.loras().then(r => r.data),
  })
  const loras = loraData?.loras || []

  async function handleUpload(e, setSlot) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const res = await systemApi.uploadImage(file)
      const { path } = res.data
      const src = URL.createObjectURL(file)
      setSlot({ file, filename: file.name, src, path })
    } catch (err) {
      alert(err.message)
    }
  }

  async function generate() {
    if (!baseImage) { alert('베이스 이미지를 선택해주세요'); return }

    const form = new FormData()
    form.append('image_path', baseImage.path || '')
    form.append('checkpoint', checkpoint)
    form.append('prompt', prompt)
    form.append('negative', negative)
    form.append('denoise', denoise)
    form.append('seed', seed)
    form.append('lora_name', loraName)
    form.append('lora_strength', loraStrength)
    if (maskBlob) form.append('mask_file', maskBlob, 'mask.png')

    await onEnqueue(() => sdApi.enqueueI2i(form))
  }
  
  useEffect(() => { bindGenerate?.(generate, !!baseImage) })

  const lastQuoteRef = useRef(null)

  useEffect(() => {
    if (!pendingQuote) return
    console.log('[quote] I2I apply', pendingQuote)
    if (pendingQuote.nonce != null && lastQuoteRef.current === pendingQuote.nonce) {
      onQuoteConsumed?.()
      return
    }
    lastQuoteRef.current = pendingQuote.nonce ?? null
    const append = !!pendingQuote.append

    if (pendingQuote.positive != null) {
      setPrompt(prev => append ? appendTags(prev, pendingQuote.positive) : pendingQuote.positive)
    }
    if (pendingQuote.negative != null) {
      setNegative(prev => append ? appendTags(prev, pendingQuote.negative) : pendingQuote.negative)
    }
    onQuoteConsumed?.()
  }, [pendingQuote])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto', width: '100%' }}>
      <div>
            <label>✅ 프롬프트</label>
            <ClearableTextarea value={prompt} onChange={setPrompt}
              style={{ height: 70, resize: 'vertical', fontSize: 11 }} />
          </div>
          <div>
            <label>❌ 네거티브</label>
            <ClearableTextarea value={negative} onChange={setNegative}
              style={{ height: 50, resize: 'vertical', fontSize: 11 }} />
          </div>

      <div>
        <label>Denoise: {denoise} (낮을수록 원본 유지)</label>
        <input type="range" min={0.1} max={1.0} step={0.05} value={denoise}
          onChange={e => setDenoise(+e.target.value)}
          style={{ padding: 0, border: 'none', background: 'none' }} />
      </div>

      {/* LoRA */}
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>🎨 LoRA</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <select value={loraName} onChange={e => setLoraName(e.target.value)} style={{ fontSize: 12 }}>
            <option value="">LoRA 없음</option>
            {loras.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <ListStatus
                error={loraError}
                empty={!loraError && !loraFetching && loras.length === 0}
                fetching={loraFetching}
                onRetry={refetchLora}
                errorText="LoRA 목록을 불러오지 못했습니다."
                emptyText="설치 폴더/models/LoRAS 에 모델 파일을 옮긴 뒤 다시 시도하세요."
              />
          {loraName && (
            <>
              <label>Strength: {loraStrength}</label>
              <input type="range" min={0} max={1} step={0.05} value={loraStrength}
                onChange={e => setLoraStrength(+e.target.value)}
                style={{ padding: 0, border: 'none', background: 'none' }} />
            </>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label>이미지 슬롯</label>

        <I2iSlot
          label="베이스" required value={baseImage}
          onUpload={e => handleUpload(e, setBaseImage)}
          onHistoryPick={() => openHistoryPicker(gen => {
            const path = gen.image_path
            const src = `${API_BASE}/api/system/image?path=${encodeURIComponent(path)}`
            setBaseImage({ file: null, filename: path.split(/[/\\]/).pop(), src, path })
          })}
          onRemove={() => setBaseImage(null)}
          onPreview={onPreview}
        />

        <I2iSlot
          label="마스크"
          value={maskSrc ? { src: maskSrc, filename: '마스크' } : null}
          onDraw={() => {
            if (!baseImage) { alert('베이스 이미지를 먼저 선택해주세요'); return }
            setShowMaskDraw(true)
          }}
          onRemove={() => { setMaskBlob(null); setMaskSrc(null) }}
          onPreview={onPreview}
        />

        <I2iSlot
          label="레퍼런스" value={refImage}
          onUpload={e => handleUpload(e, setRefImage)}
          onRemove={() => setRefImage(null)}
          onPreview={onPreview}
        />
      </div>

      {showMaskDraw && baseImage && (
        <MaskDrawOverlay
          imageSrc={baseImage.src}
          onDone={(blob, previewSrc) => {
            setMaskBlob(blob)
            setMaskSrc(previewSrc)
            setShowMaskDraw(false)
          }}
          onClose={() => setShowMaskDraw(false)}
        />
      )}
    </div>
  )
}

// ── 드롭박스 모드 패널 ─────────────────────────────────────
function T2iModePanel({
  checkpoint, tagFileData, allWeights, onEnqueue, bindGenerate,
  pendingQuote, onQuoteConsumed,
}) {
  const [negative, setNegative] = useState('')
  const [dropSelections, setDropSelections] = useState(() => {
    try {
      const saved = localStorage.getItem('dropSelections')
      return saved ? JSON.parse(saved) : {}
    } catch { return {} }
  })
  const [dropRandom, setDropRandom] = useState(() => {
    try {
      const saved = localStorage.getItem('dropRandom')
      return saved ? JSON.parse(saved) : {}
    } catch { return {} }
  })
  const [dropRandomFixed, setDropRandomFixed] = useState(() => {
    try {
      const saved = localStorage.getItem('dropRandomFixed')
      return saved ? JSON.parse(saved) : {}
    } catch { return {} }
  })
  const [promptOrder, setPromptOrder] = useState(() => {
    try {
      const saved = localStorage.getItem('promptOrder')
      return saved ? JSON.parse(saved) : []
    } catch { return [] }
  })
  const [isDraggingTag, setIsDraggingTag] = useState(false)
  const [globalNavIndex, setGlobalNavIndex] = useState(-1)
  const [globalSearch, setGlobalSearch] = useState('')
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false)
  const [openSubs, setOpenSubs] = useState(new Set())
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectedNav, setSelectedNav] = useState(null)
  const catRefs = useRef({})
  const subRefs = useRef({})
  const fuseRef = useRef(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')

  const [loraName, setLoraName]         = useState('')
  const [loraStrength, setLoraStrength] = useState(0.8)

  // 스플릿 리사이즈용
  const [topRatio, setTopRatio] = useState(0.4)
  const splitContainerRef = useRef(null)
  const isDraggingSplitRef = useRef(false)

  const sensors = useSensors(useSensor(PointerSensor, {
    activationConstraint: { distance: 5 }
  }))

  const { data: loraData, isError: loraError, isFetching: loraFetching, refetch: refetchLora } = useQuery({
    queryKey: ['loras'],
    queryFn: () => sdApi.loras().then(r => r.data),
  })
  const loras = loraData?.loras || []


  // 프롬프트 dnd useEffect
  useEffect(() => {
    setPromptOrder(prev => {
      const current = []
      for (const cat of CATEGORY_ORDER) {
        for (const sub of (CATEGORY_CONFIG[cat] || [])) {
          const subKey = `${cat}.${sub.key}`
          for (const en of (dropSelections[subKey] || [])) {
            current.push({ subKey, en, isManual: false })
          }
        }
      }
      const currentSet = new Set(current.map(t => `${t.subKey}::${t.en}`))
      const prevFiltered = prev.filter(t =>
        t.isManual || currentSet.has(`${t.subKey}::${t.en}`)
      )
      const prevSet = new Set(prevFiltered.map(t =>
        t.isManual ? `manual::${t.en}` : `${t.subKey}::${t.en}`
      ))
      const newTags = current.filter(t => !prevSet.has(`${t.subKey}::${t.en}`))
      return [...prevFiltered, ...newTags]
    })
  }, [dropSelections])

  const allTagsFlat = useMemo(() => {
    const result = []
    for (const cat of CATEGORY_ORDER) {
      for (const sub of (CATEGORY_CONFIG[cat] || [])) {
        const subKey = `${cat}.${sub.key}`
        const fileData = tagFileData[cat] || {}
        const list = getSubcategoryTags(fileData, sub.key)
        for (const t of list) {
          result.push({ ...t, cat, subKey, subLabel: sub.label })
        }
      }
    }
    return result
  }, [tagFileData])

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(globalSearch), 150)
    return () => clearTimeout(timer)
  }, [globalSearch])

  const globalResults = useMemo(() => {
    if (!debouncedSearch.trim()) return []
    if (!fuseRef.current) return []
    return fuseRef.current.search(debouncedSearch).map(r => r.item).slice(0, 30)
  }, [debouncedSearch])

  useEffect(() => {
    fuseRef.current = new Fuse(allTagsFlat, {
      keys: ['en', 'ko'], threshold: 0.4, distance: 100, includeScore: true,
    })
  }, [allTagsFlat])

  // 히스토리 프롬프트 인용 (기존 값 대체)
  const lastQuoteRef = useRef(null)

  useEffect(() => {
    if (!pendingQuote) return
    console.log('[quote] T2I apply', pendingQuote)
    // StrictMode 이중 실행 방지
    if (pendingQuote.nonce != null && lastQuoteRef.current === pendingQuote.nonce) {
      onQuoteConsumed?.()
      return
    }
    lastQuoteRef.current = pendingQuote.nonce ?? null
    const append = !!pendingQuote.append

    if (pendingQuote.positive != null) {
      const tokens = [...new Set(
        pendingQuote.positive.split(',').map(t => t.trim()).filter(Boolean)
      )]
      const selections = append ? { ...dropSelections } : {}
      const order = append ? [...promptOrder] : []

      for (const token of tokens) {
        if (order.some(p => p.en === token)) continue
        const lower = token.toLowerCase()
        const underscored = lower.replace(/ /g, '_')
        const hit = allTagsFlat.find(t =>
          t.en.toLowerCase() === underscored ||
          t.en.toLowerCase() === lower ||
          t.ko === token
        )

        if (hit) {
          const sub = (CATEGORY_CONFIG[hit.cat] || []).find(s => `${hit.cat}.${s.key}` === hit.subKey)
          const cur = selections[hit.subKey] || []
          if (cur.includes(hit.en)) continue
          if (sub?.multi || cur.length === 0) {
            selections[hit.subKey] = [...cur, hit.en]
            order.push({ subKey: hit.subKey, en: hit.en, isManual: false })
            continue
          }
        }
        // 보유 태그가 아니거나 단일 선택 칸이 이미 찬 경우 → 수동 태그로 보존
        if (!order.some(p => p.isManual && p.en === token)) {
          order.push({ subKey: null, en: token, isManual: true })
        }
      }

      if (!append) {
        setDropRandom({})
        setDropRandomFixed({})
      }
      setDropSelections(selections)
      setPromptOrder(order)
    }

    if (pendingQuote.negative != null) {
      setNegative(prev => append
        ? appendTags(prev, pendingQuote.negative)
        : dedupeTags(pendingQuote.negative))
    }

    onQuoteConsumed?.()
  }, [pendingQuote])
  
  function toggleSub(subKey) {
    setOpenSubs(prev => {
      const s = new Set(prev)
      s.has(subKey) ? s.delete(subKey) : s.add(subKey)
      return s
    })
  }

  // 스플릿 드래그 핸들러
  function handleSplitDrag(e) {
    if (!isDraggingSplitRef.current || !splitContainerRef.current) return
    const rect = splitContainerRef.current.getBoundingClientRect()
    const clientY = e.touches ? e.touches[0].clientY : e.clientY
    let ratio = (clientY - rect.top) / rect.height
    ratio = Math.min(Math.max(ratio, 0.15), 0.85)
    setTopRatio(ratio)
  }

  function stopSplitDrag() {
    isDraggingSplitRef.current = false
    window.removeEventListener('mousemove', handleSplitDrag)
    window.removeEventListener('mouseup', stopSplitDrag)
    window.removeEventListener('touchmove', handleSplitDrag)
    window.removeEventListener('touchend', stopSplitDrag)
  }

  function startSplitDrag() {
    isDraggingSplitRef.current = true
    window.addEventListener('mousemove', handleSplitDrag)
    window.addEventListener('mouseup', stopSplitDrag)
    window.addEventListener('touchmove', handleSplitDrag)
    window.addEventListener('touchend', stopSplitDrag)
  }

  async function generate() {
    const prompt = promptOrder.map(t => t.en).filter(Boolean).join(', ')
    await onEnqueue(() => sdApi.enqueueT2i({
      prompt, negative, checkpoint, lora_name: loraName, lora_strength: loraStrength,
    }))
  }

  useEffect(() => { bindGenerate?.(generate, !!checkpoint) })

  function SortableTag({ id, label, subLabel, isManual, onRemove, onClick }) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
    return (
      <div ref={setNodeRef}
        style={{
          transform: CSS.Transform.toString(transform),
          transition,
          opacity: isDragging ? 0.5 : 1,
          display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-start',
          background: 'var(--bg3)',
          border: `1px solid ${isManual ? 'var(--success)' : 'var(--accent)'}`,
          borderRadius: 4, padding: '2px 6px', fontSize: 11,
          cursor: isDragging ? 'grabbing' : 'grab',
          color: isManual ? 'var(--success)' : 'var(--accent)',
        }}
        {...attributes}
        {...listeners}
        onClick={onClick}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          {subLabel && (
            <span style={{ fontSize: 9, color: 'var(--text-dim)', marginRight: 2 }}>
              [{subLabel}]
            </span>
          )}
          {label}
          <button
            onPointerDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); onRemove() }}
            style={{ background: 'none', border: 'none', color: isManual ? 'var(--success)' : 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 11 }}
          >×</button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, width: 0, display: 'flex', flexDirection: 'column', gap: 8, overflow: 'hidden' }}>

      <div ref={splitContainerRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>

        {/* 상단 단: 검색, 프롬프트 미리보기, LoRA, 부정 프롬프트, 고급 옵션 */}
        <div style={{
          height: `${topRatio * 100}%`,
          overflowY: 'auto',
          display: 'flex', flexDirection: 'column', gap: 6,
          paddingBottom: 8,
        }}>
          
          {/* 전체 태그 검색 */}
            <input
              placeholder="🔍 전체 태그 검색..."
              value={globalSearch}
              onChange={e => { setGlobalSearch(e.target.value); setGlobalSearchOpen(true); setGlobalNavIndex(-1) }}
              onFocus={() => setGlobalSearchOpen(true)}
              onBlur={() => setTimeout(() => { setGlobalSearchOpen(false); setGlobalNavIndex(-1) }, 150)}
              onKeyDown={e => {
                if (e.key === 'ArrowDown') {
                  if (!globalSearchOpen || globalResults.length === 0) return
                  e.preventDefault()
                  setGlobalNavIndex(prev => Math.min(prev + 1, globalResults.length - 1))
                } else if (e.key === 'ArrowUp') {
                  if (!globalSearchOpen || globalResults.length === 0) return
                  e.preventDefault()
                  setGlobalNavIndex(prev => Math.max(prev - 1, 0))
                } else if (e.key === 'Enter') {
                  e.preventDefault()
                  if (globalNavIndex >= 0 && globalResults[globalNavIndex]) {
                    const t = globalResults[globalNavIndex]
                    const sub = (CATEGORY_CONFIG[t.cat] || []).find(s => `${t.cat}.${s.key}` === t.subKey)
                    // 이미 선택된 태그는 무시 (해제하지 않음, 입력·목록 유지)
                    if ((dropSelections[t.subKey] || []).includes(t.en)) return
                    setDropSelections(prev => {
                      const cur = prev[t.subKey] || []
                      if (!sub?.multi) return { ...prev, [t.subKey]: [t.en] }
                      return { ...prev, [t.subKey]: [...cur, t.en] }
                    })
                    } else if (globalSearch.trim()) {
                      const tokens = globalSearch.split(',').map(t => t.trim()).filter(Boolean)
                      const found = []
                      const manual = []

                      for (const token of tokens) {
                        const lower = token.toLowerCase()
                        const underscored = lower.replace(/ /g, '_')
                        const hit = allTagsFlat.find(t =>
                          t.en.toLowerCase() === underscored ||
                          t.en.toLowerCase() === lower ||
                          t.ko === token
                        )
                        if (hit) found.push(hit)
                        else manual.push(token.replace(/ /g, '_'))
                      }

                      if (found.length) {
                        setDropSelections(prev => {
                          const next = { ...prev }
                          for (const t of found) {
                            const sub = (CATEGORY_CONFIG[t.cat] || []).find(s => `${t.cat}.${s.key}` === t.subKey)
                            const cur = next[t.subKey] || []
                            if (cur.includes(t.en)) continue
                            next[t.subKey] = sub?.multi ? [...cur, t.en] : [t.en]
                          }
                          return next
                        })
                      }

                      const newManual = manual.filter(en => !promptOrder.some(p => p.en === en))
                      if (newManual.length) {
                        setPromptOrder(prev => [
                          ...prev,
                          ...newManual.map(en => ({ subKey: null, en, isManual: true }))
                        ])
                      }
                    } else {
                      return
                    }
                  setGlobalSearch('')
                  setGlobalSearchOpen(false)
                  setGlobalNavIndex(-1)
                }
              }}
              style={{ fontSize: 12 }}
            />
          <div style={{ position: 'relative', height: 0, marginTop: -6 }}>
            {globalSearchOpen && globalResults.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
                background: 'var(--bg2)', border: '1px solid var(--border)',
                borderRadius: 6, marginTop: 2,
                maxHeight: 280, overflowY: 'auto',
                boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
              }}>
                {globalResults.map((t, i) => {
                  const isSelected = (dropSelections[t.subKey] || []).includes(t.en)
                  const isNavActive = i === globalNavIndex
                  return (
                    <div key={`${t.subKey}-${t.en}-${i}`}
                      onMouseDown={e => {
                        // 이미 선택된 태그는 무시 (해제하지 않음). preventDefault로 입력창 포커스 유지 → 목록도 유지
                        if (isSelected) { e.preventDefault(); return }
                        const sub = (CATEGORY_CONFIG[t.cat] || []).find(s => `${t.cat}.${s.key}` === t.subKey)
                        setDropSelections(prev => {
                          const cur = prev[t.subKey] || []
                          if (!sub?.multi) return { ...prev, [t.subKey]: [t.en] }
                          return { ...prev, [t.subKey]: [...cur, t.en] }
                        })
                        setGlobalSearch('')
                        setGlobalSearchOpen(false)
                        setGlobalNavIndex(-1)
                      }}
                      onMouseEnter={() => setGlobalNavIndex(i)}
                      onMouseLeave={() => setGlobalNavIndex(-1)}
                      style={{
                        padding: '6px 10px', cursor: 'pointer', fontSize: 11,
                        display: 'flex', alignItems: 'center', gap: 8,
                        background: isNavActive ? 'var(--accent)' : isSelected ? 'var(--bg3)' : 'transparent',
                        borderBottom: '1px solid var(--border)',
                      }}
                    >
                      <span style={{ color: isNavActive ? '#fff' : 'var(--accent)', fontSize: 10, minWidth: 80 }}>
                        {t.cat} / {t.subLabel}
                      </span>
                      <span style={{ color: isNavActive ? '#fff' : isSelected ? 'var(--accent)' : 'var(--text)' }}>
                        {t.ko ? `${t.ko} (${t.en})` : t.en}
                      </span>
                      {isSelected && <span style={{ marginLeft: 'auto', color: isNavActive ? '#fff' : 'var(--accent)', fontSize: 10 }}>✓</span>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* 최종 프롬프트 미리보기 */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
            <div style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-ghost"
                  style={{ fontSize: 11, padding: '2px 8px' }}
                  disabled={promptOrder.length === 0}
                  onClick={() => {
                    setDropSelections({})
                    setDropRandom({})
                    setDropRandomFixed({})
                    setPromptOrder([])
                  }}>
                  🗑️ 초기화
                </button>
                <button className="btn btn-ghost"
                  style={{ fontSize: 11, padding: '2px 8px' }}
                  onClick={() => navigator.clipboard.writeText(promptOrder.map(t => t.en).join(', '))}>
                  📋 복사
                </button>
              </div>
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={() => setIsDraggingTag(true)}
              onDragEnd={({ active, over }) => {
                setIsDraggingTag(false)
                if (!over || active.id === over.id) return
                setPromptOrder(prev => {
                  const getId = t => t.isManual ? `manual::${t.en}` : `${t.subKey}::${t.en}`
                  const oldIdx = prev.findIndex(t => getId(t) === active.id)
                  const newIdx = prev.findIndex(t => getId(t) === over.id)
                  return arrayMove(prev, oldIdx, newIdx)
                })
              }}
            >
              <SortableContext
                items={promptOrder.map(t => t.isManual ? `manual::${t.en}` : `${t.subKey}::${t.en}`)}
                strategy={rectSortingStrategy}
              >
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, maxHeight: 150, overflowY: 'auto' }}>
                  {promptOrder.map((t) => {
                    const { subKey, en, isManual } = t
                    const cat = subKey?.split('.')[0]
                    const fileData = cat ? (tagFileData[cat] || {}) : {}
                    const subConf = cat ? (CATEGORY_CONFIG[cat] || []).find(s => `${cat}.${s.key}` === subKey) : null
                    const list = subConf ? getSubcategoryTags(fileData, subConf.key) : []
                    const item = list.find(t => t.en === en)
                    const label = item ? `${item.ko}(${en})` : en
                    const subLabel = subConf?.label || null
                    const isRandom = !isManual && dropRandom[subKey] && dropRandomFixed[subKey] === en

                    return (
                      <SortableTag
                        key={isManual ? `manual::${en}` : `${subKey}::${en}`}
                        id={isManual ? `manual::${en}` : `${subKey}::${en}`}
                        label={label}
                        subLabel={subLabel}
                        isManual={isManual}
                        onClick={() => {
                          if (isManual) {
                            setPromptOrder(prev => prev.filter(t => !(t.isManual && t.en === en)))
                          } else if (isRandom) {
                            setDropRandom(prev => ({ ...prev, [subKey]: false }))
                            setDropRandomFixed(prev => { const n = {...prev}; delete n[subKey]; return n })
                          } else {
                            setDropSelections(prev => ({
                              ...prev, [subKey]: (prev[subKey] || []).filter(t => t !== en)
                            }))
                          }
                        }}
                        onRemove={() => {
                          if (isManual) {
                            setPromptOrder(prev => prev.filter(t => !(t.isManual && t.en === en)))
                          } else if (isRandom) {
                            setDropRandom(prev => ({ ...prev, [subKey]: false }))
                            setDropRandomFixed(prev => { const n = {...prev}; delete n[subKey]; return n })
                          } else {
                            setDropSelections(prev => ({
                              ...prev, [subKey]: (prev[subKey] || []).filter(t => t !== en)
                            }))
                          }
                        }}
                      />
                    )
                  })}
                </div>
              </SortableContext>
            </DndContext>
          </div>

          {/* LoRA */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>🎨 LoRA</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <select value={loraName} onChange={e => setLoraName(e.target.value)} style={{ fontSize: 12 }}>
                <option value="">LoRA 없음</option>
                {loras.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
              <ListStatus
                    error={loraError}
                    empty={!loraError && !loraFetching && loras.length === 0}
                    fetching={loraFetching}
                    onRetry={refetchLora}
                    errorText="LoRA 목록을 불러오지 못했습니다."
                    emptyText="설치 폴더/models/LoRAS 에 모델 파일을 옮긴 뒤 다시 시도하세요."
                  />
              {loraName && (
                <>
                  <label>Strength: {loraStrength}</label>
                  <input type="range" min={0} max={1} step={0.05} value={loraStrength}
                    onChange={e => setLoraStrength(+e.target.value)}
                    style={{ padding: 0, border: 'none', background: 'none' }} />
                </>
              )}
            </div>
          </div>

          {/* 부정 프롬프트 */}
          <div>
            <label>❌ 부정 프롬프트</label>
            <ClearableTextarea value={negative} onChange={setNegative}
              style={{ height: 56, resize: 'vertical', fontSize: 11 }} />
          </div>

          {/* 고급 옵션 토글 */}
          <div>
            <button
              className="btn btn-ghost"
              style={{ width: '100%', fontSize: 11, padding: '4px 8px', textAlign: 'left' }}
              onClick={() => setShowAdvanced(v => !v)}
            >
              {showAdvanced ? '▼' : '▶'} 고급 옵션 (카테고리 네비)
            </button>

            {showAdvanced && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {CATEGORY_ORDER.map(cat => (
                    <button key={cat} className="btn btn-ghost"
                      style={{ fontSize: 11, padding: '3px 8px',
                        ...(selectedNav === cat ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                      onClick={() => {
                        setSelectedNav(cat)
                        catRefs.current[cat]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                      }}>
                      {cat}
                    </button>
                  ))}
                </div>

                {selectedNav && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {(CATEGORY_CONFIG[selectedNav] || []).map(sub => (
                      <button key={sub.key} className="btn btn-ghost"
                        style={{ fontSize: 11, padding: '2px 6px' }}
                        onClick={() => {
                          const subKey = `${selectedNav}.${sub.key}`
                          setOpenSubs(prev => {
                            const s = new Set(prev)
                            if (s.has(subKey)) { s.delete(subKey); return s }
                            s.add(subKey)
                            return s
                          })
                          setTimeout(() => {
                            subRefs.current[subKey]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                          }, 50)
                        }}>
                        {sub.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* 드래그 핸들 */}
        <div
          onMouseDown={e => { e.preventDefault(); startSplitDrag() }}
          onTouchStart={startSplitDrag}
          style={{
            height: 10, flexShrink: 0, cursor: 'row-resize',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg3)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)',
          }}
        >
          <div style={{ width: 32, height: 3, borderRadius: 2, background: 'var(--border)' }} />
        </div>

        {/* 하단 단: 카테고리 목록 */}
        <div style={{
          height: `${(1 - topRatio) * 100}%`,
          overflowY: 'auto',
          display: 'flex', flexDirection: 'column', gap: 8,
          paddingTop: 8,
          scrollPaddingTop: 8,   // scrollIntoView 가 위 여백(paddingTop)과 같은 간격으로 맞추도록: 첫 이동 시 8px 튀는 현상 제거
        }}>
          {CATEGORY_ORDER.map(cat => {
            const config = CATEGORY_CONFIG[cat] || []
            const fileData = tagFileData[cat] || {}

            const disabledSubs = new Set()
            for (const sub of config) {
              if (!sub.exclusiveWith) continue
              const subKey = `${cat}.${sub.key}`
              const hasSelection = (dropSelections[subKey] || []).length > 0
              if (hasSelection) sub.exclusiveWith.forEach(excl => disabledSubs.add(excl))
            }

            return (
              <div key={cat} ref={el => catRefs.current[cat] = el} style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10, flexShrink: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>{cat}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {config.map(sub => {
                    const subKey = `${cat}.${sub.key}`
                    const isDisabled = disabledSubs.has(subKey)
                    const isRandom = dropRandom[subKey] || false
                    const selected = dropSelections[subKey] || []
                    const isOpen = openSubs.has(subKey)
                    const list = getSubcategoryTags(fileData, sub.key)

                    const topTags = !isOpen ? [] : list
                      .filter(t => (allWeights[t.en] || 0) > 0)
                      .sort((a, b) => (allWeights[b.en] || 0) - (allWeights[a.en] || 0))
                      .slice(0, 5)

                    return (
                      <div key={subKey} ref={el => subRefs.current[subKey] = el} style={{
                        borderRadius: 6,
                        background: isDisabled ? 'var(--bg)' : 'var(--bg3)',
                        opacity: isDisabled ? 0.4 : 1,
                        pointerEvents: isDisabled ? 'none' : 'auto',
                        marginBottom: 4,
                      }}>
                        <div
                          onClick={() => !isDisabled && toggleSub(subKey)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '6px 8px', cursor: 'pointer',
                            borderRadius: isOpen ? '6px 6px 0 0' : 6,
                            borderBottom: isOpen ? '1px solid var(--border)' : 'none',
                          }}
                        >
                          <span style={{ fontSize: 11, color: 'var(--text-dim)', flex: 1 }}>
                            {sub.label}
                            {!sub.multi && <span style={{ color: 'var(--accent)', marginLeft: 4, fontSize: 10 }}>단일</span>}
                            <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>{isOpen ? '▼' : '▶'}</span>
                          </span>
                          <label
                            style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, margin: 0, cursor: 'pointer' }}
                            onClick={e => e.stopPropagation()}
                          >
                            <input type="checkbox" checked={isRandom}
                              onChange={e => {
                                const checked = e.target.checked
                                setDropRandom(prev => ({ ...prev, [subKey]: checked }))
                                if (checked) {
                                  if (list.length) {
                                    const picked = list[Math.floor(Math.random() * list.length)].en
                                    setDropRandomFixed(prev => ({ ...prev, [subKey]: picked }))
                                  }
                                } else {
                                  setDropRandomFixed(prev => { const n = {...prev}; delete n[subKey]; return n })
                                }
                              }} />
                            랜덤
                          </label>
                        </div>

                        {selected.length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, padding: '4px 8px' }}>
                            {selected.map(en => {
                              const item = list.find(t => t.en === en)
                              return (
                                <span key={en} style={{
                                  background: 'var(--accent)', color: '#fff',
                                  borderRadius: 4, padding: '1px 6px', fontSize: 11,
                                  display: 'flex', alignItems: 'center', gap: 3
                                }}>
                                  {item ? `${item.ko}(${en})` : en}
                                  <button onClick={() => setDropSelections(prev => ({
                                    ...prev, [subKey]: (prev[subKey] || []).filter(t => t !== en)
                                  }))} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: 0, fontSize: 11 }}>×</button>
                                </span>
                              )
                            })}
                          </div>
                        )}

                        {isOpen && !isRandom && (
                          <div style={{ padding: '6px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}>
                              <span style={{ fontSize: 13, marginRight: 2 }}>
                                <span style={{ color: 'var(--gold-chip)' }}>★</span> 자주 사용하는 태그
                              </span>
                              {topTags.length === 0 && (
                                <span style={{ fontSize: 10, opacity: 0.7 }}>
                                  아직 피드백이 부족합니다. 피드백이 쌓이면 자주 사용하는 태그가 여기에 표시됩니다.
                                </span>
                              )}
                              {topTags.map(t => {
                                const isSelected = selected.includes(t.en)
                                return (
                                  <button key={t.en} className="btn btn-ghost"
                                    style={{
                                      fontSize: 10, padding: '1px 6px',
                                      borderColor: isSelected ? 'var(--accent)' : 'var(--border)',
                                      color: isSelected ? 'var(--accent)' : 'var(--text)',
                                    }}
                                    onClick={() => {
                                      setDropSelections(prev => {
                                        const cur = prev[subKey] || []
                                        if (isSelected) return { ...prev, [subKey]: cur.filter(e => e !== t.en) }
                                        if (!sub.multi) return { ...prev, [subKey]: [t.en] }
                                        return { ...prev, [subKey]: [...cur, t.en] }
                                      })
                                    }}>
                                    {t.ko || t.en}
                                  </button>
                                )
                              })}
                            </div>

                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, maxHeight: 120, overflowY: 'auto', padding: '2px 0' }}>
                              {list.map(t => {
                                const isSelected = selected.includes(t.en)
                                return (
                                  <button key={t.en} className="btn btn-ghost"
                                    style={{ fontSize: 11, padding: '2px 6px',
                                      ...(isSelected ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                                    onClick={() => {
                                      setDropSelections(prev => {
                                        const cur = prev[subKey] || []
                                        if (isSelected) return { ...prev, [subKey]: cur.filter(e => e !== t.en) }
                                        if (!sub.multi) return { ...prev, [subKey]: [t.en] }
                                        return { ...prev, [subKey]: [...cur, t.en] }
                                      })
                                    }}>
                                    {t.ko}({t.en})
                                  </button>
                                )
                              })}
                              {list.length === 0 && (
                                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>데이터 없음</span>
                              )}
                            </div>
                          </div>
                        )}

                        {isOpen && isRandom && dropRandomFixed[subKey] && (
                          <div style={{ padding: '6px 8px', fontSize: 11, color: 'var(--text-dim)' }}>
                            고정: {dropRandomFixed[subKey]}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── 초기화(X) 버튼이 달린 텍스트박스 ─────────────────────
function ClearableTextarea({ value, onChange, style, ...rest }) {
  return (
    <div style={{ position: 'relative' }}>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{ ...style, paddingRight: 26 }}
        {...rest}
      />
      {value && (
        <button
          type="button"
          title="초기화"
          onClick={() => onChange('')}
          style={{
            position: 'absolute', top: 4, right: 4,
            width: 18, height: 18, padding: 0,
            border: 'none', borderRadius: 4,
            background: 'var(--bg2)', color: 'var(--text-dim)',
            cursor: 'pointer', fontSize: 12, lineHeight: '18px',
          }}
        >×</button>
      )}
    </div>
  )
}

function ListStatus({ error, empty, fetching, onRetry, errorText, emptyText }) {
  // 다시 요청하는 동안 error/empty 상태가 초기화되므로, 직전에 보이던 안내 종류를 기억해 둔다
  const [last, setLast] = useState(null) // 'error' | 'empty' | null
  useEffect(() => {
    if (error) setLast('error')
    else if (empty) setLast('empty')
    else if (!fetching) setLast(null)
  }, [error, empty, fetching])

  const kind = error ? 'error' : empty ? 'empty' : (fetching ? last : null)
  if (!kind) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, opacity: 0.8, marginTop: 4 }}>
      <span>{kind === 'error' ? errorText : emptyText}</span>
      <button type="button" onClick={onRetry} disabled={fetching}
        style={{ fontSize: 11, padding: '2px 8px', flexShrink: 0 }}>
        {fetching ? '확인 중…' : '다시 시도'}
      </button>
    </div>
  )
}