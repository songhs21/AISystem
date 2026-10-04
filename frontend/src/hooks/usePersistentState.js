// src/hooks/usePersistentState.js
import { useState, useEffect } from 'react'

/**
 * useState + localStorage 자동 저장/복원
 * setValue는 useState와 동일(함수형 업데이트 지원)
 */
export function usePersistentState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key)
      return saved !== null ? JSON.parse(saved) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
  }, [key, value])

  return [value, setValue]
}