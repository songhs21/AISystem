// src/components/ErrorBoundary.jsx
import { Component } from 'react'
import { sendClientLog } from '../utils/clientLog'

export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    sendClientLog('error', `React 렌더링 오류: ${error?.message}`,
      { stack: `${error?.stack}\n컴포넌트:${info?.componentStack}` })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ padding: 24 }}>
        <div style={{ color: 'var(--danger)', marginBottom: 8 }}>
          화면 렌더링 중 오류가 발생했습니다. 로그에 기록되었습니다.
        </div>
        <pre style={{ fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'pre-wrap' }}>
          {String(this.state.error?.message)}
        </pre>
        <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>다시 시도</button>
      </div>
    )
  }
}