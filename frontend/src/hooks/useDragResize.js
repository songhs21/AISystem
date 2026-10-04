// src/hooks/useDragResize.js
import { useCallback, useRef } from 'react'

/**
 * 패널 가장자리 드래그로 크기 조정 (포인터 캡처 사용)
 * axis: 'x' | 'y'
 * dir : 1 = 포인터가 +방향으로 가면 커짐 (왼쪽 패널의 오른쪽 모서리, 위 패널의 아래 모서리)
 *      -1 = 반대 (오른쪽 패널의 왼쪽 모서리)
 */
export function useDragResize({ value, onChange, min, max, axis = 'x', dir = 1, onDragChange }) {
  const startRef = useRef(null)

  const onPointerDown = useCallback((e) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    startRef.current = { pos: axis === 'x' ? e.clientX : e.clientY, value }
    onDragChange?.(true)
  }, [value, axis, onDragChange])

  const onPointerMove = useCallback((e) => {
    if (!startRef.current) return
    const pos = axis === 'x' ? e.clientX : e.clientY
    const next = startRef.current.value + (pos - startRef.current.pos) * dir
    onChange(Math.round(Math.min(Math.max(next, min), max)))
  }, [onChange, min, max, axis, dir])

  const onPointerUp = useCallback((e) => {
    if (!startRef.current) return
    startRef.current = null
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch {}
    onDragChange?.(false)
  }, [onDragChange])

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp }
}