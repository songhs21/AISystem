// src/pages/GeneratePage.jsx
import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { client, sdApi, historyApi } from '../api/client'
import { API_BASE } from '../api/client'
import { useSSE } from '../hooks/useSSE'
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

// ─── 카테고리 순서 ───────────────────────────────────────────────
const CATEGORY_ORDER = [
  'people', 'composition', 'character', 'hairstyle', 'body', 'Attire',
  'pose', 'fetish', 'action', 'sexual_action', 'accessories'
]


// ─── 서브카테고리 설정 ───────────────────────────────────────────
const CATEGORY_CONFIG = {
  people: [
    { key: 'people.number_of_people', label: '인원수', multi: false }
  ],
  composition: [
    { key: 'composition.angle', label: '앵글', multi: false },
    { key: 'composition.layout_and_composition', label: '구도', multi: false },
    { key: 'composition.border_layout', label: '테두리', multi: true },
    { key: 'composition.viewer_focus', label: '시선 초점', multi: false },
    { key: 'composition.body_focus', label: '신체 초점', multi: true },
    { key: 'composition.subject_focus', label: '대상 초점', multi: false },
  ],
  character: [
    { key: 'character.race', label: '종족', multi: false },
    { key: 'character.state', label: '상태', multi: true },
    { key: 'character.organization', label: '소속', multi: false },
    { key: 'character.alteration', label: '변형', multi: true },
    { key: 'character.game_character', label: '게임 캐릭터', multi: true },
  ],
  hairstyle: [
    { key: 'hairstyle.combinable.bangs', label: '앞머리', multi: true },
    { key: 'hairstyle.combinable.hair_elements', label: '헤어 요소', multi: true },
    { key: 'hairstyle.combinable.overall_style', label: '전체 스타일', multi: true },
    { key: 'hairstyle.combinable.length', label: '길이', multi: false },
    { key: 'hairstyle.combinable.curl', label: '웨이브', multi: false },
    { key: 'hairstyle.combinable.hair_color', label: '색상', multi: false },
    { key: 'hairstyle.combinable.multicolor', label: '멀티컬러', multi: true },
    { key: 'hairstyle.combinable.side_hair', label: '옆머리', multi: true },
    { key: 'hairstyle.combinable.state', label: '상태', multi: true },
    { key: 'hairstyle.combinable.facial_hair', label: '수염', multi: true },
    { key: 'hairstyle.non_combinable.specific_style', label: '특수 스타일 (단일)', multi: false },
    { key: 'hairstyle.non_combinable.alternate_style', label: '대체 스타일', multi: false },
  ],
  Attire: [
    { key: 'Attire.fabric_and_material', label: '소재', multi: true },
    { key: 'Attire.torn_damaged', label: '손상', multi: true },
    { key: 'Attire.clothing_state', label: '착용 상태', multi: true },
    { key: 'Attire.fashion', label: '패션', multi: true },
    { key: 'Attire.tops', label: '상의', multi: true, exclusiveWith: ['Attire.one_piece'] },
    { key: 'Attire.top_cutout', label: '상의 컷아웃', multi: true },
    { key: 'Attire.bottoms', label: '하의', multi: true, exclusiveWith: ['Attire.one_piece'] },
    { key: 'Attire.bottom_cutout', label: '하의 컷아웃', multi: true },
    { key: 'Attire.one_piece', label: '원피스', multi: false, exclusiveWith: ['Attire.tops', 'Attire.bottoms'] },
    { key: 'Attire.outerwear', label: '아우터', multi: true },
    { key: 'Attire.cape', label: '망토', multi: false },
    { key: 'Attire.armor', label: '갑옷', multi: true },
    { key: 'Attire.uniform', label: '유니폼', multi: false },
    { key: 'Attire.traditional', label: '전통 의상', multi: false },
    { key: 'Attire.sleeve', label: '소매', multi: true },
    { key: 'Attire.pattern_clothes', label: '패턴', multi: true },
    { key: 'Attire.pajamas', label: '파자마', multi: false },
    { key: 'Attire.print_pattern', label: '프린트', multi: true },
    { key: 'Attire.brassiere', label: '브라', multi: false },
    { key: 'Attire.panties', label: '팬티', multi: false },
    { key: 'Attire.lingerie', label: '란제리', multi: false, exclusiveWith: ['Attire.bikinis', 'Attire.one_piece_swimsuit'] },
    { key: 'Attire.bikinis', label: '비키니', multi: true, exclusiveWith: ['Attire.one_piece_swimsuit', 'Attire.lingerie'] },
    { key: 'Attire.one_piece_swimsuit', label: '원피스 수영복', multi: false, exclusiveWith: ['Attire.bikinis', 'Attire.lingerie'] },
    { key: 'Attire.underwear_general', label: '속옷 일반', multi: true },
    { key: 'Attire.legwear', label: '레그웨어', multi: true },
    { key: 'Attire.footwear', label: '신발', multi: false },
    { key: 'Attire.collar_detail', label: '칼라', multi: true },
    { key: 'Attire.cosplay', label: '코스프레', multi: false },
    { key: 'Attire.outfit_change', label: '의상 변경', multi: false },
    { key: 'Attire.apron', label: '앞치마', multi: false },
    { key: 'Attire.sarong', label: '사롱', multi: false },
  ],
  fetish: [
    { key: 'fetish.fluid', label: '체액', multi: true },
    { key: 'fetish.expression_orgasm', label: '오르가즘 표정', multi: true },
    { key: 'fetish.after_sex_state', label: '사후 상태', multi: true },
    { key: 'fetish.bdsm_restraint', label: 'BDSM', multi: true },
    { key: 'fetish.subculture_fetish', label: '서브컬처 페티시', multi: true },
    { key: 'fetish.situation_action', label: '상황/행동', multi: true },
    { key: 'fetish.visual_item', label: '시각적 아이템', multi: true },
    { key: 'fetish.sexual_features', label: '신체 특징', multi: true },
    { key: 'fetish.sexual_positions', label: '체위/자세', multi: true },
    { key: 'fetish.censorship', label: '검열', multi: false },
    { key: 'fetish.nipple_accessory', label: '유두 액세서리', multi: true },
    { key: 'fetish.full_body_nudity', label: '나체', multi: true },
  ],
  pose: [
    { key: 'combinable.head_hair_face', label: '머리/얼굴', multi: true },
    { key: 'combinable.arm_pose', label: '팔 포즈', multi: true },
    { key: 'combinable.hand_gesture', label: '손 제스처', multi: true },
    { key: 'combinable.head_hair_clothing', label: '머리/의상', multi: true },
    { key: 'combinable.clothing_action', label: '의상 동작', multi: true },
    { key: 'non_combinable.full_body_pose', label: '전신 포즈 (단일)', multi: false },
    { key: 'non_combinable.arm_pose', label: '팔 포즈 (단일)', multi: false },
    { key: 'non_combinable.leg_pose', label: '다리 포즈 (단일)', multi: false },
    { key: 'non_combinable.appeal', label: '어필 포즈', multi: true },
    { key: 'non_combinable.action_pose', label: '액션 포즈', multi: true },
  ],
  action: [
    { key: 'action.holding_weapon', label: '무기 들기', multi: true },
    { key: 'action.holding_object_generic', label: '물건 들기', multi: true },
    { key: 'action.holding_flora_animal', label: '생물/꽃 들기', multi: true },
    { key: 'action.holding_everyday_items', label: '일상 아이템', multi: true },
    { key: 'action.body_activity', label: '신체 활동', multi: false },
    { key: 'action.daily_activity', label: '일상 활동', multi: false },
    { key: 'interaction.affection_embrace', label: '애정/포옹', multi: true },
    { key: 'interaction.oral_intimacy', label: '구강 친밀', multi: true },
    { key: 'interaction.communication_expression', label: '소통/표현', multi: true },
    { key: 'interaction.playful_interaction', label: '장난', multi: true },
  ],
  sexual_action: [
    { key: 'sexual_action.insertion_sex', label: '삽입', multi: true },
    { key: 'sexual_action.non_insertion_sex', label: '비삽입', multi: true },
    { key: 'sexual_action.masturbation', label: '자위', multi: true },
    { key: 'sexual_action.group_sex', label: '그룹', multi: true },
    { key: 'sexual_action.special_situations', label: '특수 상황', multi: true },
  ],
  accessories: [
    { key: 'accessory.headwear.hat', label: '모자', multi: false },
    { key: 'accessory.headwear.helmet', label: '헬멧', multi: false },
    { key: 'accessory.headwear.crown', label: '왕관', multi: false },
    { key: 'accessory.headwear.hood', label: '후드', multi: false },
    { key: 'accessory.headwear.headband', label: '헤드밴드', multi: false },
    { key: 'accessory.headwear.veil', label: '베일', multi: false },
    { key: 'accessory.hair_accessory.hair_ornament', label: '헤어 장식', multi: true },
    { key: 'accessory.hair_accessory.hairpin', label: '헤어핀', multi: true },
    { key: 'accessory.hair_accessory.hairband', label: '머리띠', multi: false },
    { key: 'accessory.hair_accessory.hair_tie', label: '머리끈', multi: false },
    { key: 'accessory.eyewear', label: '안경/고글', multi: false },
    { key: 'accessory.earwear', label: '귀걸이', multi: true },
    { key: 'accessory.neckwear.necktie', label: '넥타이', multi: false },
    { key: 'accessory.neckwear.bowtie', label: '나비넥타이', multi: false },
    { key: 'accessory.neckwear.choker', label: '초커', multi: false },
    { key: 'accessory.neckwear.necklace', label: '목걸이', multi: true },
    { key: 'accessory.neckwear.scarf', label: '스카프', multi: false },
    { key: 'accessory.handwear.gloves', label: '장갑', multi: false },
    { key: 'accessory.handwear.ring', label: '반지', multi: true },
    { key: 'accessory.armwear.bracelet', label: '팔찌', multi: true },
    { key: 'accessory.armwear.armband', label: '완장', multi: true },
    { key: 'accessory.bodywear.belt', label: '벨트', multi: false },
    { key: 'accessory.bodywear.harness', label: '하네스', multi: false },
    { key: 'accessory.legwear_accessory.thigh', label: '허벅지 스트랩', multi: true },
    { key: 'accessory.legwear_accessory.garter', label: '가터', multi: false },
    { key: 'accessory.jewelry.general', label: '주얼리', multi: true },
    { key: 'accessory.bag', label: '가방', multi: false },
    { key: 'accessory.misc.ribbon', label: '리본', multi: true },
    { key: 'accessory.mask_costume.mask', label: '마스크', multi: false },
  ],
  body: [
    { key: 'body.body_shape', label: '체형', multi: true },
    { key: 'body.breast_size', label: '가슴 사이즈', multi: false },
    { key: 'body.makeup.eye', label: '아이 메이크업', multi: true },
    { key: 'body.makeup.lip', label: '립', multi: true },
    { key: 'body.makeup.face', label: '페이스', multi: true },
    { key: 'body.nail.hand', label: '손톱', multi: true },
    { key: 'body.facial_hair', label: '수염', multi: true },
    { key: 'body.piercing', label: '피어싱', multi: true },
    { key: 'body.tattoo_marking.motif', label: '문신', multi: true },
    { key: 'body.bandage_injury', label: '붕대/부상', multi: true },
  ],
}


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

// ── 퍼지 검색 유틸 ──────────────────
function buildFuse(list) {
  return new Fuse(list, {
    keys: ['en', 'ko'],
    threshold: 0.4,      // 0.0 완전일치 ~ 1.0 전부매칭, 0.4가 실용적
    distance: 100,
    includeScore: true,
  })
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────────
export default function GeneratePage() {
  const [mode, setMode] = useState('dropdown')
  const [checkpoint, setCheckpoint] = useState('')
  const [negative, setNegative] = useState('')
  const [result, setResult] = useState(null)
  const [passType, setPassType] = useState('문제 없음')
  const [likedTags, setLikedTags] = useState(new Set())
  const [dislikedTags, setDislikedTags] = useState(new Set())
  const [falseTags, setFalseTags] = useState(new Set())
  const [score, setScore] = useState(5)
  const [tags, setTags] = useState([])
  const [tagPanelOpen, setTagPanelOpen] = useState(true)
  const [usedPrompt, setUsedPrompt] = useState('')

  // 드롭박스 모드 state
  const [dropSelections, setDropSelections] = useState(() => {
    try {
      const saved = localStorage.getItem('dropSelections')
      return saved ? JSON.parse(saved) : {}
    } catch { return {} }
  })  // { 'cat.subKey': [en, ...] }
  const [dropRandom, setDropRandom] = useState(() => {
    try {
      const saved = localStorage.getItem('dropRandom')
      return saved ? JSON.parse(saved) : {}
    } catch { return {} }
  })          // { 'cat.subKey': bool }
  const [dropRandomFixed, setDropRandomFixed] = useState(() => {
    try {
      const saved = localStorage.getItem('dropRandomFixed')
      return saved ? JSON.parse(saved) : {}
    } catch { return {} }
  }) // { 'cat.subKey': en }
  const [dropSearch, setDropSearch] = useState({})           // { 'cat.subKey': string }
  const [promptOrder, setPromptOrder] = useState([])
  const [isDraggingTag, setIsDraggingTag] = useState(false)

  // 텍스트 모드 state
  const [textPrompt, setTextPrompt] = useState('')
  const [textRandom, setTextRandom] = useState({})           // { cat: bool }
  const [textRandomFixed, setTextRandomFixed] = useState({}) // { cat: en }
  const [globalSearch, setGlobalSearch] = useState('')
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false)
  const [openSubs, setOpenSubs] = useState(new Set())
    // i2i 모드 state
  const [i2iBaseImage, setI2iBaseImage] = useState(null)   // { path, filename, src }
  const [i2iMaskImage, setI2iMaskImage] = useState(null)
  const [i2iRefImage, setI2iRefImage]   = useState(null)
  const [i2iPrompt, setI2iPrompt]       = useState('')
  const [i2iNegative, setI2iNegative]   = useState('')
  const [i2iDenoise, setI2iDenoise]     = useState(0.7)
  const [i2iSeed, setI2iSeed]           = useState(-1)
  const [showHistoryPicker, setShowHistoryPicker] = useState(false) // 히스토리 이미지 피커
  const [i2iOverlay, setI2iOverlay]     = useState(null)  // 오버레이로 볼 이미지 src

  // 프로그레스
  const { progress, statusText, running, error, run } = useSSE()

  // 최종 프롬프트 state
  const [selectedNav, setSelectedNav] = useState(null)
  const catRefs = useRef({})
  const subRefs = useRef({})

  // 초기 state 선언 시 localStorage에서 복원

  

  

  const sensors = useSensors(useSensor(PointerSensor, {
    activationConstraint: { distance: 5 }  // 드래그 최소 임계점 (px)
  }))

  // ── 체크포인트 ──
  const { data: cpData } = useQuery({
    queryKey: ['checkpoints'],
    queryFn: () => sdApi.checkpoints().then(r => r.data),
  })
  const checkpoints = cpData?.checkpoints || []
  useEffect(() => {
    if (checkpoints.length && !checkpoint) setCheckpoint(checkpoints[1])
  }, [checkpoints])


  // ── 네거티브 초기값 ──
  const { data: constants } = useQuery({
    queryKey: ['constants'],
    queryFn: () => client.get('/api/system/constants').then(r => r.data),
  })

  useEffect(() => {
    if (constants?.negative_base && !negative) setNegative(constants.negative_base)
  }, [constants])

  // 프롬프트 dnd useEffect
  useEffect(() => {
  setPromptOrder(prev => {
    const current = []
    for (const cat of CATEGORY_ORDER) {
      for (const sub of (CATEGORY_CONFIG[cat] || [])) {
        const subKey = `${cat}.${sub.key}`
        for (const en of (dropSelections[subKey] || [])) {
          current.push({ subKey, en })
        }
      }
    }
    const currentSet = new Set(current.map(t => `${t.subKey}::${t.en}`))
    const prevFiltered = prev.filter(t => currentSet.has(`${t.subKey}::${t.en}`))
    const prevSet = new Set(prevFiltered.map(t => `${t.subKey}::${t.en}`))
    const newTags = current.filter(t => !prevSet.has(`${t.subKey}::${t.en}`))
    return [...prevFiltered, ...newTags]
  })
}, [dropSelections])

  // 태그 리스트 변동 시 저장
  useEffect(() => {
    localStorage.setItem('dropSelections', JSON.stringify(dropSelections))
  }, [dropSelections])

  useEffect(() => {
    localStorage.setItem('dropRandom', JSON.stringify(dropRandom))
  }, [dropRandom])

  useEffect(() => {
    localStorage.setItem('dropRandomFixed', JSON.stringify(dropRandomFixed))
  }, [dropRandomFixed])

  // ── 태그 JSON 로드 ──
  const { data: tagFileData = {} } = useQuery({
    queryKey: ['tag-file-data'],
    queryFn: async () => {
      const results = {}
      await Promise.all(
        CATEGORY_ORDER.map(async (cat) => {
          try {
            const filename = cat === 'Attire' ? 'Attire.json' : `${cat}.json`
            const res = await client.get(`/api/system/tags/${filename}`)
            // 최상위 키 벗기지 않고 그대로 저장 (경로는 config key에 포함)
            results[cat] = res.data
          } catch { results[cat] = {} }
        })
      )
      return results
    },
    staleTime: Infinity,
  })

  // 텍스트 모드 랜덤용 플랫 리스트
  const tagData = useMemo(() => {
    const r = {}
    for (const cat of CATEGORY_ORDER) r[cat] = flattenTags(tagFileData[cat] || {})
    return r
  }, [tagFileData])

  // 번역 맵 { en: ko }
  const koMap = useMemo(() => {
    const map = {}
    for (const cat of CATEGORY_ORDER) flattenTagsToMap(tagFileData[cat] || {}, map)
    return map
  }, [tagFileData])

  // 전체 가중치 로드 (staleTime: Infinity)
  const { data: allWeights = {} } = useQuery({
    queryKey: ['all-tag-weights'],
    queryFn: () => historyApi.allTagWeights().then(r => r.data),
    staleTime: Infinity,
  })

  // ── 미리보기 ──
  const dropPrompt = useMemo(() => {
    return promptOrder.map(t => t.en).join(', ')
  }, [promptOrder])

  const textFinalPrompt = useMemo(() => {
    const parts = []
    if (textPrompt.trim()) parts.push(textPrompt.trim())
    for (const cat of CATEGORY_ORDER) {
      if (textRandom[cat]) {
        const fixed = textRandomFixed[cat]
        if (fixed) parts.push(fixed)
      }
    }
    return parts.join(', ')
  }, [textPrompt, textRandom, textRandomFixed])

  const finalPrompt = mode === 'dropdown' ? dropPrompt : textFinalPrompt

    // ── 전체 태그 플랫 리스트 (useMemo, koMap 선언 다음) ──
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

  // ── 전체 검색 결과 ──
  const globalResults = useMemo(() => {
    if (!globalSearch.trim()) return []
    const fuse = new Fuse(allTagsFlat, {
      keys: ['en', 'ko'],
      threshold: 0.4,
      distance: 100,
      includeScore: true,
    })
    return fuse.search(globalSearch).map(r => r.item).slice(0, 30)
  }, [globalSearch, allTagsFlat])

  // img 1600px 체크 함수
  function checkImageSize(file) {
    return new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => {
        URL.revokeObjectURL(img.src)
        if (img.naturalWidth > 1600 || img.naturalHeight > 1600) {
          reject(new Error(`이미지 크기 초과: ${img.naturalWidth}×${img.naturalHeight} (최대 1600px)`))
        } else {
          resolve({ width: img.naturalWidth, height: img.naturalHeight })
        }
      }
      img.src = URL.createObjectURL(file)
    })
  }

  async function handleI2iUpload(e, setSlot) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      await checkImageSize(file)
      const src = URL.createObjectURL(file)
      setSlot({ file, filename: file.name, src, fromHistory: false })
    } catch (err) {
      alert(err.message)
    }
  }

  function handleHistoryPick(gen) {
    // 업스케일 이미지면 원본 선택
    const isUpscaled = gen.upscaled_image &&
      gen.image_path.replace(/[^/\\]*$/, '') + gen.upscaled_image === gen.image_path
    const path = gen.image_path
    const src = `${API_BASE}/api/system/image?path=${encodeURIComponent(path)}`
    setI2iBaseImage({ file: null, filename: path.split(/[/\\]/).pop(), src, path, fromHistory: true })
    setShowHistoryPicker(false)
  }

  // ── 생성 ──
    async function generate() {
      setResult(null)
      setTags([])
      setLikedTags(new Set())
      setDislikedTags(new Set())
      setFalseTags(new Set())

      if (mode === 'i2i') {
        if (!i2iBaseImage) { alert('베이스 이미지를 선택해주세요'); return }

        // 히스토리 이미지면 path 직접 사용, 업로드면 서버로 전송 필요
        let imagePath = i2iBaseImage.path || ''

        if (!i2iBaseImage.fromHistory) {
          // 파일 업로드 → /api/system/upload 로 전송 (추후 엔드포인트 추가 필요)
          // 임시: COMFY_INPUT에 저장하는 엔드포인트 필요
          alert('파일 업로드 엔드포인트 미구현 — 히스토리 이미지를 사용해주세요')
          return
        }

        await run(
          sdApi.i2iUrl(),
          {
            image_path: imagePath,
            checkpoint,
            prompt: i2iPrompt,
            negative: i2iNegative || negative,
            denoise: i2iDenoise,
            seed: i2iSeed,
          },
          {
            onDone: async (data) => {
              setResult(data)
            }
          }
        )
        return
      }

      // 기존 드롭박스 모드 생성
      const parts = []
      for (const cat of CATEGORY_ORDER) {
        for (const sub of (CATEGORY_CONFIG[cat] || [])) {
          const subKey = `${cat}.${sub.key}`
          if (dropRandom[subKey]) {
            const fixed = dropRandomFixed[subKey]
            if (fixed) parts.push(fixed)
          } else {
            parts.push(...(dropSelections[subKey] || []))
          }
        }
      }

      const prompt = parts.filter(Boolean).join(', ')
      console.log('[Generate] mode:', mode, 'prompt:', prompt)

      await run(
        sdApi.generateUrl(),
        { prompt, negative, checkpoint },
        {
          onDone: async (data) => {
            setResult(data)
            try {
              const gen = await historyApi.generation(data.gen_id)
              setUsedPrompt(gen.data.prompt || '')
              setTags(gen.data.tags || [])
            } catch(e) { console.error('태그 조회 실패:', e) }
          }
        }
      )
    }

  // ── 피드백 저장 ──
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
  }

  // 서브 카테고리 열고 닫기
  function toggleSub(subKey) {
    setOpenSubs(prev => {
      const s = new Set(prev)
      s.has(subKey) ? s.delete(subKey) : s.add(subKey)
      return s
    })
  }

  // 드래그 앤 드롭
  function SortableTag({ id, label, onRemove, onClick }) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
    return (
      <div ref={setNodeRef}
        style={{
          transform: CSS.Transform.toString(transform),
          transition,
          opacity: isDragging ? 0.5 : 1,
          display: 'inline-flex', alignItems: 'center', gap: 3,
          background: 'var(--bg3)', border: '1px solid var(--accent)',
          borderRadius: 4, padding: '2px 6px', fontSize: 11,
          cursor: isDragging ? 'grabbing' : 'grab',
          color: 'var(--accent)',
        }}
        {...attributes}
        {...listeners}
        onClick={onClick}  // ← 클릭 시 제거
      >
        {label}
        <button
          onPointerDown={e => e.stopPropagation()}
          onClick={e => { e.stopPropagation(); onRemove() }}
          style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 11 }}
        >×</button>
      </div>
    )
  }

  
  // ── JSX ──
  return (
    <div style={{ display: 'flex', width: '100%', height: '100%', flex: 1, overflow: 'hidden' }}>

      {/* 좌: 이미지 뷰어 + 생성 버튼 */}
      <div style={{ width: '28%', minWidth: 320, flexShrink: 0, display: 'flex', flexDirection: 'column', padding: 16, gap: 10, borderRight: '1px solid var(--border)' }}>

        {/* 체크포인트 */}
        <div>
          <label>체크포인트</label>
          <select value={checkpoint} onChange={e => setCheckpoint(e.target.value)}>
            {checkpoints.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        {/* 이미지 뷰어 */}
        <div style={{ flex: 1, overflow: 'hidden', borderRadius: 8, background: 'var(--bg2)', border: '1px solid var(--border)' }}>
          {result
            ? <ImageViewer src={`${API_BASE}/api/system/image?path=${encodeURIComponent(result.image_path)}`} />
            : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                생성된 이미지가 여기에 표시됩니다
              </div>
          }
        </div>

        {/* 진행바 */}
        {(running || progress > 0) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div className="progress-bar">
              <div className="progress-bar-fill" style={{ width: `${progress * 100}%` }} />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{statusText}</span>
          </div>
        )}
        {error && <div style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>}

        <button className="btn btn-primary" onClick={generate} disabled={running || !checkpoint}>
          {running ? '생성 중...' : '이미지 생성'}
        </button>
      </div>

      {/* 중: 긍정 프롬프트 입력 (스크롤) */}
      <div style={{ flex: 1, width: 0, display: 'flex', flexDirection: 'column', padding: 16, gap: 10, overflow: 'hidden' }}>

        {/* 고정 헤더 */}
        <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 6, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>

          {/* 모드 전환 */}
          <div style={{ display: 'flex', gap: 4 }}>
            {['dropdown', 'i2i'].map(m => (
              <button key={m} className="btn btn-ghost"
                style={{ fontSize: 11, padding: '4px 10px', ...(mode === m ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                onClick={() => setMode(m)}>
                {m === 'dropdown' ? '🔽 드롭박스' : '🖼️ i2i'}
              </button>
            ))}
          </div>
          
          {/* 전체 태그 검색 */}
          <div style={{ position: 'relative' }}>
            <input
              placeholder="🔍 전체 태그 검색..."
              value={globalSearch}
              onChange={e => { setGlobalSearch(e.target.value); setGlobalSearchOpen(true) }}
              onFocus={() => setGlobalSearchOpen(true)}
              onBlur={() => setTimeout(() => setGlobalSearchOpen(false), 150)}
              style={{ fontSize: 12 }}
            />
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
                  return (
                    <div key={`${t.subKey}-${t.en}-${i}`}
                      onMouseDown={() => {
                        const sub = (CATEGORY_CONFIG[t.cat] || []).find(s => `${t.cat}.${s.key}` === t.subKey)
                        setDropSelections(prev => {
                          const cur = prev[t.subKey] || []
                          if (isSelected) return { ...prev, [t.subKey]: cur.filter(e => e !== t.en) }
                          if (!sub?.multi) return { ...prev, [t.subKey]: [t.en] }
                          return { ...prev, [t.subKey]: [...cur, t.en] }
                        })
                        setGlobalSearch('')
                        setGlobalSearchOpen(false)
                      }}
                      style={{
                        padding: '6px 10px', cursor: 'pointer', fontSize: 11,
                        display: 'flex', alignItems: 'center', gap: 8,
                        background: isSelected ? 'var(--bg3)' : 'transparent',
                        borderBottom: '1px solid var(--border)',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg3)'}
                      onMouseLeave={e => e.currentTarget.style.background = isSelected ? 'var(--bg3)' : 'transparent'}
                    >
                      <span style={{ color: 'var(--accent)', fontSize: 10, minWidth: 80 }}>
                        {t.cat} / {t.subLabel}
                      </span>
                      <span style={{ color: isSelected ? 'var(--accent)' : 'var(--text)' }}>
                        {t.ko ? `${t.ko} (${t.en})` : t.en}
                      </span>
                      {isSelected && <span style={{ marginLeft: 'auto', color: 'var(--accent)', fontSize: 10 }}>✓</span>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* 1차 카테고리 버튼 */}
          {mode === 'dropdown' && (
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
          )}

          {/* 2차 카테고리 버튼 */}
          {mode === 'dropdown' && selectedNav && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {(CATEGORY_CONFIG[selectedNav] || []).map(sub => (
                <button key={sub.key} className="btn btn-ghost"
                  style={{ fontSize: 11, padding: '2px 6px' }}
                  onClick={() => {
                    const subKey = `${selectedNav}.${sub.key}`
                    setOpenSubs(prev => {
                      const s = new Set(prev)
                      if (s.has(subKey)) {
                        s.delete(subKey)
                        return s
                      }
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

          {/* 최종 프롬프트 미리보기 */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 6, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>최종 프롬프트 미리보기</span>
              <button className="btn btn-ghost"
                style={{ fontSize: 11, padding: '2px 8px' }}
                onClick={() => navigator.clipboard.writeText(promptOrder.map(t => t.en).join(', '))}>
                📋 복사
              </button>
            </div>
            {/* 최종 프롬프트 미리보기 — 드롭박스 모드 */}
            {mode === 'dropdown' && (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragStart={() => setIsDraggingTag(true)}
                onDragEnd={({ active, over }) => {
                  setIsDraggingTag(false)
                  if (!over || active.id === over.id) return
                  setPromptOrder(prev => {
                    const oldIdx = prev.findIndex(t => `${t.subKey}::${t.en}` === active.id)
                    const newIdx = prev.findIndex(t => `${t.subKey}::${t.en}` === over.id)
                    return arrayMove(prev, oldIdx, newIdx)
                  })
                }}
              >
                <SortableContext
                  items={promptOrder.map(t => `${t.subKey}::${t.en}`)}
                  strategy={rectSortingStrategy}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, maxHeight: 80, }}>
                    {promptOrder.length === 0
                      ? <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>비어있음</span>
                      : promptOrder.map(({ subKey, en }) => {
                          // 랜덤 태그인지 체크
                          const isRandom = dropRandom[subKey] && dropRandomFixed[subKey] === en
                          // 한글 라벨 찾기
                          const cat = subKey.split('.')[0]
                          const fileData = tagFileData[cat] || {}
                          const subConf = (CATEGORY_CONFIG[cat] || []).find(s => `${cat}.${s.key}` === subKey)
                          const list = subConf ? getSubcategoryTags(fileData, subConf.key) : []
                          const item = list.find(t => t.en === en)
                          const label = item ? `${item.ko}(${en})` : en

                          return (
                           <SortableTag
                            key={`${subKey}::${en}`}
                            id={`${subKey}::${en}`}
                            label={label}
                            onClick={() => {
                              if (isRandom) {
                                setDropRandom(prev => ({ ...prev, [subKey]: false }))
                                setDropRandomFixed(prev => { const n = {...prev}; delete n[subKey]; return n })
                              } else {
                                setDropSelections(prev => ({
                                  ...prev, [subKey]: (prev[subKey] || []).filter(t => t !== en)
                                }))
                              }
                            }}
                            onRemove={() => {
                              if (isRandom) {
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
                        })
                    }
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </div>
        </div>

        {/* 스크롤 영역 */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>

          {/* 드롭박스 모드 */}
          {mode === 'dropdown' && CATEGORY_ORDER.map(cat => {
            const config = CATEGORY_CONFIG[cat] || []
            const fileData = tagFileData[cat] || {}

            // 배타 관계 계산
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
                        {/* 2차 카테고리 헤더 — 항상 표시 */}
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
                          {/* 랜덤 체크박스 — 항상 표시 */}
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

                        {/* 선택된 배지 — 항상 표시 */}
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

                        {/* 펼쳐진 상태에서만 표시 */}
                        {isOpen && !isRandom && (
                          <div style={{ padding: '6px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {/* ★ 추천 칩 */}
                            {topTags.length > 0 && (
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}>
                                <span style={{ fontSize: 13, marginRight: 2 }}>
                                  <span style={{ color: 'var(--gold-chip)' }}>★</span> 자주 사용하는 태그
                                </span>
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
                            )}

                            {/* 태그 후보 목록 */}
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, maxHeight: 120, overflowY: 'auto', padding: '2px 0' }}>
                              {(() => {
                                const fuse = buildFuse(list)
                                const filtered = list  // 검색은 전체 검색창으로 통합됐으니 전체 표시
                                return filtered.map(t => {
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
                                })
                              })()}
                              {list.length === 0 && (
                                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>데이터 없음</span>
                              )}
                            </div>
                          </div>
                        )}

                        {/* 랜덤 고정값 표시 */}
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

          {/* i2i 모드 */}
          {mode === 'i2i' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

              {/* 프롬프트 */}
              <div>
                <label>✅ 긍정 프롬프트</label>
                <textarea value={i2iPrompt} onChange={e => setI2iPrompt(e.target.value)}
                  placeholder="비워두면 공백으로 전달"
                  style={{ height: 70, resize: 'vertical' }} />
              </div>
              <div>
                <label>❌ 부정 프롬프트</label>
                <textarea value={i2iNegative} onChange={e => setI2iNegative(e.target.value)}
                  placeholder="비워두면 기본 네거티브 사용"
                  style={{ height: 50, resize: 'vertical' }} />
              </div>

              {/* Denoise */}
              <div>
                <label>Denoise: {i2iDenoise} (낮을수록 원본 유지)</label>
                <input type="range" min={0.1} max={1.0} step={0.05} value={i2iDenoise}
                  onChange={e => setI2iDenoise(+e.target.value)}
                  style={{ padding: 0, border: 'none', background: 'none' }} />
              </div>

              {/* 이미지 슬롯 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label>이미지 슬롯</label>

                {/* 베이스 */}
                <I2iSlot
                  label="베이스"
                  required
                  value={i2iBaseImage}
                  onUpload={e => handleI2iUpload(e, setI2iBaseImage)}
                  onHistoryPick={() => setShowHistoryPicker(true)}
                  onRemove={() => setI2iBaseImage(null)}
                  onPreview={src => setI2iOverlay(src)}
                />

                {/* 마스크 */}
                <I2iSlot
                  label="마스크"
                  value={i2iMaskImage}
                  onUpload={e => handleI2iUpload(e, setI2iMaskImage)}
                  onRemove={() => setI2iMaskImage(null)}
                  onPreview={src => setI2iOverlay(src)}
                />

                {/* 레퍼런스 */}
                <I2iSlot
                  label="레퍼런스"
                  value={i2iRefImage}
                  onUpload={e => handleI2iUpload(e, setI2iRefImage)}
                  onRemove={() => setI2iRefImage(null)}
                  onPreview={src => setI2iOverlay(src)}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 우: 부정 프롬프트 */}
      <div style={{ width: '18%', minWidth: 200, flexShrink: 0, borderLeft: '1px solid var(--border)', padding: 16, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
        <label>❌ 부정 프롬프트</label>
        <textarea value={negative} onChange={e => setNegative(e.target.value)}
          style={{ flex: 1, minHeight: 120, resize: 'vertical' }} />
      </div>

      {/* 태그 패널 오버레이 */}
      {result && tags.length > 0 && (
        <div style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: tagPanelOpen ? '55%' : '40px', minWidth: tagPanelOpen ? 320 : 40,
          background: 'var(--bg2)',
          borderLeft: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
          transition: 'width 0.2s ease',
          zIndex: 100,
          boxShadow: tagPanelOpen ? '-4px 0 16px rgba(0,0,0,0.3)' : 'none',
        }}>
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center', whiteSpace: 'nowrap' }}>
            <button className="btn btn-ghost" onClick={() => setTagPanelOpen(v => !v)}>
              {tagPanelOpen ? '▶' : '◀'}
            </button>
            {tagPanelOpen && (
              <>
                <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>패스 유형</span>
                {['문제 없음', '그림체', '인체 디테일', '마음에 들지 않음'].map(p => (
                  <button key={p} className="btn btn-ghost"
                    style={{ padding: '3px 8px', fontSize: 11, ...(passType === p ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}) }}
                    onClick={() => setPassType(p)}>{p}</button>
                ))}
              </>
            )}
          </div>
          {tagPanelOpen && (
            <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
              {passType !== '마음에 들지 않음' && (
                <>
                  <PromptTags prompt={usedPrompt} />
                  <TagPanel tags={tags} koMap={koMap} liked={likedTags} disliked={dislikedTags} passed={falseTags}
                    onLike={tag => setLikedTags(prev => { const s = new Set(prev); s.has(tag) ? s.delete(tag) : (s.add(tag), dislikedTags.delete(tag), falseTags.delete(tag)); return s })}
                    onDislike={tag => setDislikedTags(prev => { const s = new Set(prev); s.has(tag) ? s.delete(tag) : (s.add(tag), likedTags.delete(tag), falseTags.delete(tag)); return s })}
                    onPass={tag => setFalseTags(prev => { const s = new Set(prev); s.has(tag) ? s.delete(tag) : (s.add(tag), likedTags.delete(tag), dislikedTags.delete(tag)); return s })}
                  />
                  <div style={{ padding: 12, borderTop: '1px solid var(--border)' }}>
                    <label>Score: {score}</label>
                    <input type="range" min={0} max={10} value={score}
                      onChange={e => setScore(+e.target.value)}
                      style={{ padding: 0, border: 'none', background: 'none', width: '100%' }} />
                  </div>
                </>
              )}
            </div>
          )}
          {tagPanelOpen && (
            <div style={{ padding: 12, borderTop: '1px solid var(--border)' }}>
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={saveFeedback}>저장</button>
            </div>
          )}
        </div>
      )}
      {/* 이미지 오버레이 */}
      {i2iOverlay && (
        <div
          onClick={() => setI2iOverlay(null)}
          style={{
            position: 'fixed', inset: 0, zIndex: 400,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <img src={i2iOverlay} style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8 }} />
        </div>
      )}

      {/* 히스토리 이미지 피커 */}
      {showHistoryPicker && (
        <HistoryImagePicker
          onPick={handleHistoryPick}
          onClose={() => setShowHistoryPicker(false)}
        />
      )}
    </div>
  )
}

// ── i2i 슬롯 컴포넌트 ─────────────────────────────────────
function I2iSlot({ label, required, value, onUpload, onHistoryPick, onRemove, onPreview }) {
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
          <label style={{ margin: 0 }}>
            <input type="file" accept="image/*" onChange={onUpload} style={{ display: 'none' }} />
            <span className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px', cursor: 'pointer' }}>📁 업로드</span>
          </label>
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