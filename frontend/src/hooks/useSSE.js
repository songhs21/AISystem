// src/hooks/useSSE.js
import { useState, useCallback, useRef } from 'react'

/**
 * POST 기반 SSE 스트림 훅
 * FastAPI StreamingResponse (text/event-stream) 소비
 */
export function useSSE() {
  const [progress, setProgress] = useState(0)
  const [statusText, setStatusText] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const run = useCallback(async (url, body, { onDone } = {}) => {
    setRunning(true)
    setProgress(0)
    setStatusText('')
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const isFormData = body instanceof FormData
      const res = await fetch(url, {
        method: 'POST',
        headers: isFormData ? {} : { 'Content-Type': 'application/json' },
        body: isFormData ? body : JSON.stringify(body),
        signal: controller.signal,
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()  // 미완성 라인 보관

        let eventType = null
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (eventType === 'progress') {
              setProgress(data.value)
              setStatusText(data.text)
            } else if (eventType === 'done') {
              setProgress(1)
              setStatusText('완료!')
              onDone?.(data)
            } else if (eventType === 'error') {
              setError(data.message)
            }
            eventType = null
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setRunning(false)
    }
  }, [])

  const abort = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { progress, statusText, running, error, run, abort }
}
