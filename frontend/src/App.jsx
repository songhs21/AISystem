// src/App.jsx
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import GeneratePage from './pages/GeneratePage'
import HistoryPage from './pages/HistoryPage'
import LLMPage from './pages/LLMPage'
import SystemStatus from './components/SystemStatus'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30000 } }
})

const TABS = [
  { id: 'generate', label: '🖼️ 생성' },
  { id: 'history',  label: '📋 히스토리' },
  { id: 'llm',      label: '🤖 LLM' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('generate')

  return (
    <QueryClientProvider client={queryClient}>
      <div className="app">
        <header className="app-header">
          <span className="app-title">AISystem</span>
          <nav className="tab-nav">
            {TABS.map(tab => (
              <button
                key={tab.id}
                className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
          <SystemStatus />
        </header>

        <main className="app-main">
          <div
            style={{
              display: activeTab === 'generate' ? 'flex' : 'none',
              flex: 1,
              width: '100%',
              height: '100%'
            }}
          >
            <GeneratePage />
          </div>

          <div
            style={{
              display: activeTab === 'history' ? 'flex' : 'none',
              flex: 1,
              width: '100%',
              height: '100%'
            }}
          >
            <HistoryPage />
          </div>

          <div
            style={{
              display: activeTab === 'llm' ? 'flex' : 'none',
              flex: 1,
              width: '100%',
              height: '100%'
            }}
          >
            <LLMPage />
          </div>
        </main>
      </div>
    </QueryClientProvider>
  )
}
