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