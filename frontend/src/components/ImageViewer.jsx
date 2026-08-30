// src/components/ImageViewer.jsx
import { useRef, useState, useEffect, useCallback } from 'react'

export default function ImageViewer({ src, style = {} }) {
  const containerRef = useRef(null)
  const [scale, setScale]   = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const dragStart = useRef(null)

  // 이미지 바뀌면 리셋
  useEffect(() => { setScale(1); setOffset({ x: 0, y: 0 }) }, [src])

  // 휠 줌
  const onWheel = useCallback((e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    setScale(s => Math.min(Math.max(s * delta, 0.2), 8))
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [onWheel])

  // 드래그 패닝
  const onMouseDown = (e) => {
    e.preventDefault()
    setDragging(true)
    dragStart.current = { x: e.clientX - offset.x, y: e.clientY - offset.y }
  }
  const onMouseMove = (e) => {
    if (!dragging || !dragStart.current) return
    setOffset({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y })
  }
  const onMouseUp = () => setDragging(false)

  // 더블클릭 리셋
  const onDoubleClick = () => { setScale(1); setOffset({ x: 0, y: 0 }) }

  return (
    <div
      ref={containerRef}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onDoubleClick={onDoubleClick}
      style={{
        position: 'relative',
        overflow: 'hidden',
        background: 'var(--bg)',
        borderRadius: 'var(--radius)',
        cursor: dragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        minHeight: 300,
        ...style,
      }}
    >
      <img
        src={src}
        alt=""
        draggable={false}
        style={{
          display: 'block',
          maxWidth: '100%',
          transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
          transformOrigin: 'center center',
          transition: dragging ? 'none' : 'transform 0.05s',
          pointerEvents: 'none',
        }}
      />
      <div style={{
        position: 'absolute', bottom: 6, right: 8,
        fontSize: 11, color: 'var(--text-dim)', pointerEvents: 'none',
      }}>
        {Math.round(scale * 100)}% · 더블클릭 리셋
      </div>
    </div>
  )
}
