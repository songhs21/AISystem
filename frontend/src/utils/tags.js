// src/utils/tags.js
export function dedupeTags(text) {
  const seen = new Set()
  return (text || '')
    .split(',')
    .map(t => t.trim())
    .filter(t => {
      if (!t) return false
      const k = t.toLowerCase()
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
    .join(', ')
}

export function toTagLine(text) {
  return dedupeTags((text || '').replace(/\s*\n+\s*/g, ', '))
}

export function appendTags(prev, add) {
  return dedupeTags(prev ? `${prev}, ${add}` : add)
}

export function appendText(prev, add) {
  const p = (prev || '').trimEnd()
  return p ? `${p}\n${add}` : add
}