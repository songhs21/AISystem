// src/pages/HistoryPage.jsx
import { useState, useMemo, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { historyApi, sdApi } from '../api/client'
import { API_BASE } from '../api/client'
import { useSSE } from '../hooks/useSSE'
import ImageViewer from '../components/ImageViewer'
import InpaintCanvas from '../components/InpaintCanvas'
import TagPanel from '../components/TagPanel'

const PAGE_SIZE = 10

const PASS_FILTER_OPTIONS = ['전체', '그림체', '인체 디테일', '마음에 들지 않음']
const PASS_TYPE_MAP = { '그림체': 'style', '인체 디테일': 'quality', '마음에 들지 않음': 'dislike' }
const SCORE_OPTIONS = ['적용 안함', '피드백 없음', '이상', '이하', '동일']

export default function HistoryPage() {
  const queryClient = useQueryClient()

  // 필터 상태
  const [passFilter, setPassFilter]       = useState('전체')
  const [scoreMode, setScoreMode]         = useState('적용 안함')
  const [scoreVal, setScoreVal]           = useState(5)
  const [includedTags, setIncludedTags]   = useState([])
  const [excludedTags, setExcludedTags]   = useState([])
  const [includeMode, setIncludeMode]     = useState('AND')
  const [showImages, setShowImages]       = useState(true)
  const [showFilter, setShowFilter]       = useState(false)
  const [editTarget, setEditTarget] = useState(null)  // { gen, feedback }

  // 페이지
  const [page, setPage] = useState(1)

  // 선택된 gen (편집/인페인팅)
  const [selectedId, setSelectedId]     = useState(null)
  const [inpaintTarget, setInpaintTarget] = useState(null)  // image_path

  // 업스케일 SSE
  const upscaleSSE = useSSE()

  // 데이터 조회
  const { data: gensData, isLoading } = useQuery({
    queryKey: ['generations'],
    queryFn: () => historyApi.generations().then(r => r.data),
  })
  const generations = gensData?.generations || []

  const { data: upscaleModels } = useQuery({
    queryKey: ['upscale-models'],
    queryFn: () => sdApi.upscaleModels().then(r => r.data),
  })
  const modelList = upscaleModels?.models || []

  const [selectedUpscaler, setSelectedUpscaler] = useState('')

  // 피드백 bulk 조회
  const genIds = generations.map(g => g.id)
  const { data: feedbackMap = {} } = useQuery({
    queryKey: ['feedbacks', genIds],
    queryFn: () => historyApi.feedbacks(genIds).then(r => r.data),
    enabled: genIds.length > 0,
  })

  // 클라이언트 사이드 필터 (즉각 반응)
  const filtered = useMemo(() => {
    let list = generations

    // 태그 필터
    list = list.filter(gen => {
      const tagSet = new Set(gen.tags.map(t => t.tag))
      if (excludedTags.some(t => tagSet.has(t))) return false
      if (includedTags.length) {
        if (includeMode === 'AND') return includedTags.every(t => tagSet.has(t))
        else return includedTags.some(t => tagSet.has(t))
      }
      return true
    })

    // 패스 필터
    if (passFilter !== '전체') {
      const target = PASS_TYPE_MAP[passFilter]
      list = list.filter(g => feedbackMap[g.id]?.pass_type === target)
    }

    // 점수 필터
    if (scoreMode !== '적용 안함') {
      list = list.filter(g => {
        const s = feedbackMap[g.id]?.score ?? null
        if (scoreMode === '피드백 없음') return s === null
        if (scoreMode === '이상') return s !== null && s >= scoreVal
        if (scoreMode === '이하') return s !== null && s <= scoreVal
        if (scoreMode === '동일') return s !== null && s === scoreVal
        return true
      })
    }

    return list
  }, [generations, feedbackMap, excludedTags, includedTags, includeMode, passFilter, scoreMode, scoreVal])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageGens = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  // 업스케일
  async function doUpscale(gen) {
    if (!selectedUpscaler) return
    upscaleSSE.run(
      sdApi.upscaleUrl(),
      { gen_id: gen.id, image_path: gen.image_path, upscale_model: selectedUpscaler, checkpoint: gen.checkpoint, prompt: gen.prompt },
      { onDone: () => queryClient.invalidateQueries(['generations']) }
    )
  }

// 프롬프트 표기
  function PromptTags({ prompt }) {
  const tags = (prompt || '').split(',').map(t => t.trim()).filter(t => t)

  return (
    <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.8 }}>
      {tags.map((tag, i) => (
        <span key={i} style={{
          display: 'inline-block', margin: '2px 3px',
          padding: '1px 6px', borderRadius: 4,
          background: 'var(--bg3)', border: '1px solid var(--border)',
        }}>{tag}</span>
      ))}
    </div>
  )
}

  // 전체 태그 목록 (필터 멀티셀렉트용)
  const allTags = useMemo(() => {
    const s = new Set()
    generations.forEach(g => g.tags.forEach(t => s.add(t.tag)))
    return [...s].sort()
  }, [generations])

  if (isLoading) return <div style={{ padding: 16, color: 'var(--text-dim)' }}>로딩 중...</div>

  // 인페인팅 모드
  if (inpaintTarget) {
    const gen = generations.find(g => g.image_path === inpaintTarget || g.upscaled_image === inpaintTarget)
    return (
      <InpaintCanvas
        imagePath={inpaintTarget}
        genId={gen?.id}
        checkpoint={gen?.checkpoint}
        prompt={gen?.prompt}
        onClose={() => setInpaintTarget(null)}
        onDone={() => { setInpaintTarget(null); queryClient.invalidateQueries(['generations']) }}
      />
    )
  }

  return (
    <div style={{ display: 'flex', width:'100%', height: '100%', minHeight: 0, flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>

      {/* 툴바 */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
        <button className="btn btn-ghost" onClick={() => queryClient.invalidateQueries(['generations'])}>🔄 새로고침</button>
        <button className="btn btn-ghost" onClick={() => setShowImages(v => !v)}>
          {showImages ? '🖼️ 이미지 숨기기' : '🖼️ 이미지 보기'}
        </button>
        <button className="btn btn-ghost" onClick={() => setShowFilter(v => !v)}>
          🔍 필터 {showFilter ? '닫기' : '설정'}
        </button>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-dim)' }}>
          {filtered.length}개 / 전체 {generations.length}개
        </span>
      </div>

      {/* 필터 패널 */}
      {showFilter && (
        <div className="card" style={{ margin: '8px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>

            {/* 패스 필터 */}
            <div>
              <label>패스 유형</label>
              <div style={{ display: 'flex', gap: 4 }}>
                {PASS_FILTER_OPTIONS.map(o => (
                  <button key={o} className="btn btn-ghost"
                    style={{ padding: '3px 8px', fontSize: 11, ...(passFilter === o ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                    onClick={() => { setPassFilter(o); setPage(1) }}
                  >{o}</button>
                ))}
              </div>
            </div>

            {/* 점수 필터 */}
            <div>
              <label>점수 필터</label>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                {SCORE_OPTIONS.map(o => (
                  <button key={o} className="btn btn-ghost"
                    style={{ padding: '3px 8px', fontSize: 11, ...(scoreMode === o ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                    onClick={() => { setScoreMode(o); setPage(1) }}
                  >{o}</button>
                ))}
                {scoreMode !== '적용 안함' && scoreMode !== '피드백 없음' && (
                  <input type="number" min={0} max={10} value={scoreVal}
                    onChange={e => setScoreVal(+e.target.value)}
                    style={{ width: 50 }}
                  />
                )}
              </div>
            </div>

            {/* 포함/제외 태그 */}
            <div style={{ flex: 1, minWidth: 240 }}>
              <label>포함 태그 조건</label>
              <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
                {['AND', 'OR'].map(m => (
                  <button key={m} className="btn btn-ghost"
                    style={{ padding: '3px 8px', fontSize: 11, ...(includeMode === m ? { borderColor: 'var(--accent)' } : {}) }}
                    onClick={() => setIncludeMode(m)}
                  >{m}</button>
                ))}
              </div>
              <TagMultiSelect label="✅ 포함" options={allTags} value={includedTags} onChange={v => { setIncludedTags(v); setPage(1) }} />
              <TagMultiSelect label="🚫 제외" options={allTags} value={excludedTags} onChange={v => { setExcludedTags(v); setPage(1) }} />
            </div>
          </div>
        </div>
      )}

      {/* 페이지 네비 */}
      <div style={{ padding: '6px 16px', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
        <button className="btn btn-ghost" disabled={currentPage <= 1} onClick={() => setPage(p => p - 1)}>◀ 이전</button>
        <input type="number" min={1} max={totalPages} value={currentPage}
          onChange={e => setPage(+e.target.value)}
          style={{ width: 56, textAlign: 'center' }}
        />
        <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>/ {totalPages}</span>
        <button className="btn btn-ghost" disabled={currentPage >= totalPages} onClick={() => setPage(p => p + 1)}>다음 ▶</button>
      </div>

      {/* 이미지 목록 */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 16px 16px' }}>
        {pageGens.map(gen => {
          const feedback = feedbackMap[gen.id]

          return (
            <div key={gen.id} className="card" style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', gap: 12 }}>

                {/* 이미지 */}
                {showImages && gen.image_path && (
                  <div style={{ width: '35%', maxWidth: 900, minWidth:300, flexShrink: 0 }}>
                    <ImageViewer src={`${API_BASE}/api/system/image?path=${encodeURIComponent(gen.image_path)}`} style={{ width: '100%', aspectRatio: '1/1', height:'auto' }} />
                  </div>
                )}

                {/* 정보 */}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>📅 {gen.created_at}</div>
                  <div style={{ fontSize: 12 }}>
                    <span style={{ color: 'var(--text-dim)' }}>모델: </span>
                    {gen.checkpoint?.split(/[/\\]/).pop()}
                  </div>
                  <PromptTags prompt={gen.prompt} />

                  {feedback && (
                    <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
                      {feedback.score != null && <span>⭐ {feedback.score}/10</span>}
                      {feedback.pass_type && <span style={{ color: 'var(--danger)' }}>패스: {feedback.pass_type}</span>}
                    </div>
                  )}

                  {/* 업스케일 상태 */}
                  <div style={{ fontSize: 11, color: gen.upscaled_image ? 'var(--success)' : 'var(--text-dim)' }}>
                    🔍 업스케일: {gen.upscaled_image ? `✅ ${gen.upscaled_image}` : '❌'}
                  </div>

                  {/* 액션 버튼 */}
                  <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                    {!gen.upscaled_image && (
                      <>
                        <select value={selectedUpscaler} onChange={e => setSelectedUpscaler(e.target.value)}
                          style={{ width: 160, fontSize: 11, padding: '4px 6px' }}>
                          <option value="">업스케일 모델 선택</option>
                          {modelList.map(m => <option key={m}>{m}</option>)}
                        </select>
                        <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }}
                          disabled={!selectedUpscaler || upscaleSSE.running}
                          onClick={() => doUpscale(gen)}
                        >🔼 업스케일</button>
                      </>
                    )}

                    <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }}
                      onClick={() => {
                        const path = gen.upscaled_image
                          ? `${gen.image_path.replace(/[^/\\]*$/, '')}${gen.upscaled_image}`
                          : gen.image_path
                        setInpaintTarget(path)
                      }}
                    >🖌️ 인페인팅</button>

                    <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }}
                      onClick={() => setEditTarget(editTarget?.gen.id === gen.id ? null : { gen, feedback })}
                    >⚙️ 피드백 편집</button>
                  </div>

                  {/* 업스케일 진행 */}
                  {upscaleSSE.running && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div className="progress-bar">
                        <div className="progress-bar-fill" style={{ width: `${upscaleSSE.progress * 100}%` }} />
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{upscaleSSE.statusText}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 피드백 편집 오버레이 ← 맨 아래 닫는 </div> 바로 앞에 추가 */}
              {editTarget && (
                <>
                  <div
                    onClick={() => setEditTarget(null)}
                    style={{
                      position: 'absolute', inset: 0, zIndex: 100,
                    }}
                  />
                  <div style={{
                    position: 'absolute', top: 0, right: 0, bottom: 0,
                    width: '35%',
                    minWidth: 320,
                    maxWidth: 520,
                    background: 'var(--bg2)',
                    borderLeft: '1px solid var(--border)',
                    display: 'flex', flexDirection: 'column',
                    animation: 'slideIn 0.2s ease',
                    zIndex: 101,
                  }}>
                    <div style={{
                      padding: '10px 14px',
                      borderBottom: '1px solid var(--border)',
                      display: 'flex', alignItems: 'center', gap: 8,
                      flexShrink: 0,
                    }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>⚙️ 피드백 편집</span>
                      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>#{editTarget.gen.id}</span>
                      <button className="btn btn-ghost"
                        style={{ marginLeft: 'auto', padding: '3px 8px', fontSize: 11 }}
                        onClick={() => setEditTarget(null)}
                      >✕</button>
                    </div>

                    <PromptTags prompt={gen.prompt} />

                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                      <FeedbackEditorPanel
                        gen={editTarget.gen}
                        feedback={editTarget.feedback}
                        onSave={() => {
                          queryClient.invalidateQueries(['feedbacks'])
                          setEditTarget(null)
                        }}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )
        })}

        {pageGens.length === 0 && (
          <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-dim)' }}>
            표시할 이미지가 없습니다.
          </div>
        )}
      </div>
    </div>
  )
}


// ── 태그 멀티셀렉트 (간단 구현) ──────────────────────────
function TagMultiSelect({ label, options, value, onChange }) {
  const [input, setInput] = useState('')
  const filtered = options.filter(o => o.includes(input) && !value.includes(o)).slice(0, 10)

  return (
    <div style={{ marginBottom: 6 }}>
      <label>{label}</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
        {value.map(v => (
          <span key={v} style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 6px', fontSize: 11 }}>
            {v}
            <button onClick={() => onChange(value.filter(t => t !== v))}
              style={{ marginLeft: 4, background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>×</button>
          </span>
        ))}
      </div>
      <input placeholder="태그 검색..." value={input} onChange={e => setInput(e.target.value)} style={{ marginBottom: 4 }} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {filtered.map(o => (
          <button key={o} className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 6px' }}
            onClick={() => { onChange([...value, o]); setInput('') }}
          >{o}</button>
        ))}
      </div>
    </div>
  )
}


// ── 피드백 편집기 ─────────────────────────────────────────
function FeedbackEditorPanel({ gen, feedback, onSave }) {
  const [passType, setPassType] = useState(
    feedback?.pass_type === 'style'   ? '그림체' :
    feedback?.pass_type === 'quality' ? '인체 디테일' :
    feedback?.pass_type === 'dislike' ? '마음에 들지 않음' : '문제 없음'
  )
  const [liked, setLiked]       = useState(new Set(feedback?.liked_tags || []))
  const [disliked, setDisliked] = useState(new Set(feedback?.disliked_tags || []))
  const [passed, setPassed]     = useState(new Set(feedback?.false_tags || []))
  const [score, setScore]       = useState(feedback?.score ?? 5)

  async function save() {
    await historyApi.saveFeedback({
      generation_id: gen.id,
      score: passType === '마음에 들지 않음' ? null : score,
      liked_tags:    [...liked],
      disliked_tags: [...disliked],
      false_tags:    [...passed],
      pass_type: {
        '문제 없음': null, '그림체': 'style',
        '인체 디테일': 'quality', '마음에 들지 않음': 'dislike'
      }[passType],
      pass_reasons: [],
    })
    onSave()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* 패스 유형 */}
      <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 4, flexWrap: 'wrap', flexShrink: 0 }}>
        {['문제 없음', '그림체', '인체 디테일', '마음에 들지 않음'].map(p => (
          <button key={p} className="btn btn-ghost"
            style={{ fontSize: 11, padding: '3px 8px',
              ...(passType === p ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
            onClick={() => setPassType(p)}
          >{p}</button>
        ))}
      </div>

      {passType !== '마음에 들지 않음' && (
        <>
          {/* 태그 목록 */}
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
            <TagPanel
              tags={gen.tags}
              liked={liked} disliked={disliked} passed={passed}
              onLike={tag => setLiked(prev => {
                const s = new Set(prev)
                s.has(tag) ? s.delete(tag) : (s.add(tag), disliked.delete(tag), passed.delete(tag))
                return s
              })}
              onDislike={tag => setDisliked(prev => {
                const s = new Set(prev)
                s.has(tag) ? s.delete(tag) : (s.add(tag), liked.delete(tag), passed.delete(tag))
                return s
              })}
              onPass={tag => setPassed(prev => {
                const s = new Set(prev)
                s.has(tag) ? s.delete(tag) : (s.add(tag), liked.delete(tag), disliked.delete(tag))
                return s
              })}
            />
          </div>

          {/* 스코어 */}
          <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
            <label>Score: {score}</label>
            <input type="range" min={0} max={10} value={score}
              onChange={e => setScore(+e.target.value)}
              style={{ width: '100%', padding: 0, border: 'none', background: 'none' }} />
          </div>
        </>
      )}

      {/* 저장 */}
      <div style={{ padding: 12, borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <button className="btn btn-primary" style={{ width: '100%' }} onClick={save}>
          변경 사항 저장
        </button>
      </div>
    </div>
  )
}
