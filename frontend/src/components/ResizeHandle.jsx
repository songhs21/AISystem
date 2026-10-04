// src/components/ResizeHandle.jsx
export default function ResizeHandle({ axis = 'x', style, ...handlers }) {
  const horizontal = axis === 'x'
  return (
    <div
      {...handlers}
      style={{
        position: 'absolute', zIndex: 80, touchAction: 'none',
        cursor: horizontal ? 'col-resize' : 'row-resize',
        ...(horizontal ? { top: 0, bottom: 0, width: 6 } : { left: 0, right: 0, height: 6 }),
        ...style,
      }}
    />
  )
}