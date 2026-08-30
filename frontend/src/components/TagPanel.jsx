// src/components/TagPanel.jsx
import { useQuery } from '@tanstack/react-query'
import { historyApi } from '../api/client'

const TAG_CATEGORY_ORDER = [
  'quality', 'framing', 'hair_color', 'hair_color_pattern', 'hair_style',
  'front_hair_style', 'hair_accessory', 'eyes_color', 'emotion',
  'pose', 'body_features', 'top_style', 'bra_style', 'bra_color',
  'bottom_style', 'underwear_style', 'socks_style', 'outfit_general',
  'outfit_swimwear', 'outfit_costume', 'outfit_color', 'cloth_color_pattern',
  'footwear_style', 'footwear_color', 'design_details', 'props_accessories',
  'props_food', 'props_objects', 'props_furniture', 'background',
]

const CAT_KO = {
  quality: '퀄리티', framing: '프레이밍', hair_color: '머리색',
  hair_color_pattern: '머리색 패턴', hair_style: '헤어스타일',
  front_hair_style: '앞머리', hair_accessory: '헤어 악세사리',
  eyes_color: '눈색', emotion: '표정', pose: '포즈',
  body_features: '신체', top_style: '상의', bra_style: '브라',
  bra_color: '브라색', bottom_style: '하의', underwear_style: '속옷',
  socks_style: '양말', outfit_general: '의상 전체', outfit_swimwear: '수영복',
  outfit_costume: '코스튬', outfit_color: '의상색', cloth_color_pattern: '패턴',
  footwear_style: '신발', footwear_color: '신발색', design_details: '디자인',
  props_accessories: '악세사리', props_food: '음식', props_objects: '소품',
  props_furniture: '가구', background: '배경',
}

const EXTRA_CATEGORIES = ['unregistered', 'meta', 'rating']

export default function TagPanel({ tags, koMap = {}, liked, disliked, passed, onLike, onDislike, onPass }) {
  const tagValues = tags.map(t => t.tag)
  const { data: weightMap = {} } = useQuery({
    queryKey: ['tag-weights', tagValues],
    queryFn: () => historyApi.tagWeights(tagValues).then(r => r.data),
    enabled: tagValues.length > 0,
  })

  const grouped = {}
  for (const t of tags) {
    const cat = t.category || '기타'
    const displayCat = EXTRA_CATEGORIES.includes(cat) ? '기타' : cat
    if (!grouped[displayCat]) grouped[displayCat] = []
    grouped[displayCat].push(t)
  }

  const renderOrder = [...TAG_CATEGORY_ORDER, '기타']

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
      {renderOrder.map(cat => {
        const list = grouped[cat] || []
        if (!list.length) return null
        const label = CAT_KO[cat] || cat

        return (
          <div key={cat} style={{ marginBottom: 12 }}>
            <div style={{
              textAlign: 'center', fontSize: 11, color: 'var(--text-dim)',
              borderBottom: '1px solid var(--border)', paddingBottom: 4, marginBottom: 6,
            }}>
              ────{label}────
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4 }}>
              {list.map(t => {
                const tag = t.tag
                const ko = koMap[tag]
                const w = weightMap[tag]
                const wStr = w != null ? `W${w.toFixed(2)}` : 'W0.00'
                const isLiked = liked.has(tag)
                const isDisliked = disliked.has(tag)
                const isPassed = passed.has(tag)

                // 태그 표시: 한글 있으면 "한글\n(영어)" 형식
                const tagLabel = ko
                  ? `${ko}\n(${tag})`
                  : tag

                return (
                  <div key={tag} style={{ display: 'contents' }}>
                    <button
                      className={`tag-btn ${isLiked ? 'liked' : ''}`}
                      onClick={() => onLike(tag)}
                    >{`${isLiked ? '✅' : '👍'} ${tagLabel}\n${wStr}`}</button>
                    <button
                      className={`tag-btn ${isDisliked ? 'disliked' : ''}`}
                      onClick={() => onDislike(tag)}
                    >{`${isDisliked ? '❌' : '👎'} ${tagLabel}\n${wStr}`}</button>
                    <button
                      className={`tag-btn ${isPassed ? 'passed' : ''}`}
                      onClick={() => onPass(tag)}
                    >{`${isPassed ? '🚫' : '⚠️'} ${tagLabel}\n${wStr}`}</button>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}